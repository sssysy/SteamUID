"""Steam WebAuth 认证协议。

只推进 IAuthenticationService 登录协议与令牌获取，凭据落库 / 会话校验由调用方处理。
"""

import os
from types import TracebackType
from base64 import b64encode
from binascii import hexlify
from collections.abc import Mapping

from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding

from .client import (
    STEAM_DOMAINS,
    DEFAULT_USER_AGENT,
    apply_cookies,
    make_async_client,
    request_ok_response,
)
from .models import (
    AuthLoginDone,
    RsaKeyPayload,
    AppConfirmDone,
    AuthCodeResult,
    RsaKeyResponse,
    AuthStartResult,
    AppConfirmResult,
    AuthLoginPending,
    SteamCredentials,
    AppConfirmWaiting,
    AccessTokenResponse,
    PollAuthStatusResponse,
    BeginAuthSessionResponse,
)
from .endpoints import (
    API_BASE_DEFAULT,
    AUTH_GET_RSA_KEY,
    AUTH_POLL_STATUS,
    AUTH_BEGIN_CREDENTIALS,
    AUTH_UPDATE_GUARD_CODE,
    COMMUNITY_BASE_DEFAULT,
    AUTH_GENERATE_ACCESS_TOKEN,
)

_TAG = "账户认证"


def rsa_encrypt_password(publickey_mod: str, publickey_exp: str, password: str) -> str:
    """用 Steam 下发的 RSA 公钥做 PKCS#1 v1.5 加密。"""
    public_key = rsa.RSAPublicNumbers(e=int(publickey_exp, 16), n=int(publickey_mod, 16)).public_key()
    ciphertext = public_key.encrypt(password.encode("utf-8"), rsa_padding.PKCS1v15())
    return b64encode(ciphertext).decode("ascii")


def generate_session_id() -> str:
    """生成 24 位十六进制字符串作为 sessionid。"""
    return hexlify(os.urandom(12)).decode("ascii")


async def generate_access_token_for_app(
    refresh_token: str,
    steamid: str,
    *,
    base_url: str = API_BASE_DEFAULT,
    proxy: str | None = None,
    timeout: float = 15.0,
) -> str:
    """用 refresh_token 换新的 access_token，响应缺字段时抛 ValueError。"""
    url = f"{base_url.rstrip('/')}{AUTH_GENERATE_ACCESS_TOKEN}"
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(
            client,
            "POST",
            url,
            tag=_TAG,
            data={"refresh_token": refresh_token, "steamid": steamid},
            timeout=timeout,
        )

    payload: AccessTokenResponse = resp.json()
    response = payload["response"]
    if "access_token" not in response:
        raise ValueError("刷新 access_token 返回数据异常")
    return response["access_token"]


class SteamWebAuth:
    """对接官方 IAuthenticationService 的登录协议客户端。"""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        *,
        base_url: str = API_BASE_DEFAULT,
        proxy: str | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.client_id: str = ""
        self.request_id: str = ""
        self.steam_id: str = ""
        self.allowed_confirmations: list[int] = []
        self.refresh_token: str = ""
        self.access_token: str = ""
        self.session_id: str = ""
        self.logged_on: bool = False

        self.client = make_async_client(
            proxy=proxy,
            timeout=timeout,
            headers={
                "Origin": COMMUNITY_BASE_DEFAULT,
                "Referer": f"{COMMUNITY_BASE_DEFAULT}/",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "SteamWebAuth":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _get_rsa_key(self) -> RsaKeyPayload:
        resp = await request_ok_response(
            self.client,
            "GET",
            self._url(AUTH_GET_RSA_KEY),
            tag=_TAG,
            params={"account_name": self.username},
            timeout=self.timeout,
        )
        payload: RsaKeyResponse = resp.json()
        response = payload["response"]
        if "publickey_mod" not in response or "publickey_exp" not in response:
            raise ValueError("无法获取密码加密密钥，请检查账号名是否输入正确")
        return response

    async def start_session(self, username: str = "", password: str = "") -> AuthStartResult:
        """发起初次认证会话，返回已登录或待两步验证两种结果。"""
        if username:
            self.username = username
        if password:
            self.password = password
        if not self.username or not self.password:
            raise ValueError("账号名或密码不能为空")

        rsa_info = await self._get_rsa_key()
        data: Mapping[str, str] = {
            "device_friendly_name": DEFAULT_USER_AGENT,
            "account_name": self.username,
            "encrypted_password": rsa_encrypt_password(
                rsa_info["publickey_mod"],
                rsa_info["publickey_exp"],
                self.password,
            ),
            "encryption_timestamp": rsa_info["timestamp"],
            "remember_login": "1",
            "platform_type": "2",
            "persistence": "1",
            "website_id": "Community",
        }

        resp = await request_ok_response(
            self.client,
            "POST",
            self._url(AUTH_BEGIN_CREDENTIALS),
            tag=_TAG,
            data=data,
            timeout=self.timeout,
        )
        payload: BeginAuthSessionResponse = resp.json()
        response = payload["response"]
        if "client_id" not in response or "request_id" not in response:
            raise ValueError("账号或密码错误，请重新输入")

        self.client_id = str(response["client_id"])
        self.request_id = str(response["request_id"])
        if "steamid" in response:
            self.steam_id = str(response["steamid"])

        confirmations = response["allowed_confirmations"] if "allowed_confirmations" in response else []
        self.allowed_confirmations = [
            item["confirmation_type"] for item in confirmations if "confirmation_type" in item
        ]

        if not await self._poll_status():
            return AuthLoginPending(
                ok=True,
                done=False,
                need_2fa=True,
                can_app_confirm=3 in self.allowed_confirmations,
                hint=self._manual_hint(),
            )

        self._finalize_login()
        return AuthLoginDone(
            ok=True,
            done=True,
            need_2fa=False,
            steamid64=self.steam_id,
        )

    def _manual_hint(self) -> str:
        """按可用的确认方式给出验证码输入提示。"""
        if 1 in self.allowed_confirmations:
            return "请输入发送至您绑定邮箱的验证码"
        if 3 in self.allowed_confirmations:
            return "请在 Steam App 中确认登录，或输入 5 位动态令牌"
        return "请输入手机 Steam 应用中的 5 位动态令牌码"

    async def _poll_status(self) -> bool:
        """轮询一次授权状态；尚未拿到令牌返回 False。"""
        if not self.client_id or not self.request_id:
            raise ValueError("登录会话已失效，请重新发起登录")

        resp = await request_ok_response(
            self.client,
            "POST",
            self._url(AUTH_POLL_STATUS),
            tag=_TAG,
            data={"client_id": self.client_id, "request_id": self.request_id},
            timeout=self.timeout,
        )
        payload: PollAuthStatusResponse = resp.json()
        response = payload["response"]
        if "refresh_token" not in response or "access_token" not in response:
            return False

        self.refresh_token = response["refresh_token"]
        self.access_token = response["access_token"]
        return True

    async def submit_2fa_code(self, code: str) -> AuthCodeResult:
        """提交两步验证码；验证未通过时抛 ValueError。"""
        if not self.client_id or not self.steam_id:
            raise ValueError("登录会话已失效，请重新发起登录")

        normalized = code.strip().upper()
        if not normalized:
            raise ValueError("验证码不能为空")

        code_type = 1 if 1 in self.allowed_confirmations and 2 not in self.allowed_confirmations else 2
        await request_ok_response(
            self.client,
            "POST",
            self._url(AUTH_UPDATE_GUARD_CODE),
            tag=_TAG,
            data={
                "client_id": self.client_id,
                "steamid": self.steam_id,
                "code": normalized,
                "code_type": str(code_type),
            },
            timeout=self.timeout,
        )

        if not await self._poll_status():
            raise ValueError("两步验证码错误或已失效，请重新输入")

        self._finalize_login()
        return AuthCodeResult(ok=True, done=True, steamid64=self.steam_id)

    async def check_app_confirmation(self) -> AppConfirmResult:
        """轮询手机端确认是否已完成。"""
        if self.logged_on:
            return AppConfirmDone(ok=True, done=True, steamid64=self.steam_id)
        if not self.client_id or not self.request_id:
            raise ValueError("登录会话已失效，请重新发起登录")

        if not await self._poll_status():
            return AppConfirmWaiting(
                ok=False,
                done=False,
                msg="尚未检测到手机端确认，请在手机 App 上点击[允许]",
            )

        self._finalize_login()
        return AppConfirmDone(ok=True, done=True, steamid64=self.steam_id)

    def _finalize_login(self) -> None:
        self.session_id = generate_session_id()
        self.logged_on = True
        apply_cookies(
            self.client,
            {
                "sessionid": self.session_id,
                "steamLoginSecure": f"{self.steam_id}||{self.access_token}",
            },
            STEAM_DOMAINS,
        )

    def get_credentials(self) -> SteamCredentials:
        """导出本次登录得到的凭据，供调用方自行落库。"""
        cookies: dict[str, str] = {}
        for cookie in self.client.cookies.jar:
            name = cookie.name
            value = cookie.value
            if name is None or value is None:
                continue
            cookies[name] = value

        return SteamCredentials(
            steamid64=self.steam_id,
            account_name=self.username,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            session_id=self.session_id,
            cookies=cookies,
        )
