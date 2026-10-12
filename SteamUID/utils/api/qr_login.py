"""Steam 扫码登录协议（IAuthenticationService QR 流程）。

只推进 BeginAuthSessionViaQR / PollAuthSessionStatus 两个接口与令牌获取，
凭据落库 / 会话校验由调用方处理。
"""

from types import TracebackType

from gsuid_core.logger import logger

from .auth import steamid_from_access_token
from .client import DEFAULT_USER_AGENT, make_async_client, request_ok_response
from .models import (
    QrReady,
    QrWaiting,
    QrChallenge,
    QrPollResult,
    QrPollResponse,
    BeginQrResponse,
)
from .endpoints import (
    AUTH_BEGIN_QR,
    API_BASE_DEFAULT,
    AUTH_POLL_STATUS,
    COMMUNITY_BASE_DEFAULT,
)

_TAG = "扫码登录"

# EAuthTokenPlatformType_WebBrowser = 2 + Community：拿网页会话用的令牌
_PLATFORM_TYPE = "2"
_WEBSITE_ID = "Community"


class SteamQrLogin:
    """对接官方 IAuthenticationService 的扫码登录客户端。"""

    def __init__(
        self,
        *,
        api_base_url: str = API_BASE_DEFAULT,
        proxy: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.timeout = timeout
        self.api_base_url = api_base_url.rstrip("/")
        self.client_id = ""
        self.request_id = ""
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

    async def __aenter__(self) -> "SteamQrLogin":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def begin(self) -> QrChallenge:
        """发起扫码会话，返回二维码内容与轮询参数。"""
        resp = await request_ok_response(
            self.client,
            "POST",
            f"{self.api_base_url}{AUTH_BEGIN_QR}",
            tag=_TAG,
            data={
                "device_friendly_name": DEFAULT_USER_AGENT,
                "platform_type": _PLATFORM_TYPE,
                "website_id": _WEBSITE_ID,
            },
            timeout=self.timeout,
        )
        payload: BeginQrResponse = resp.json()
        response = payload["response"]
        if (
            "client_id" not in response
            or "challenge_url" not in response
            or "request_id" not in response
            or "interval" not in response
        ):
            raise ValueError("扫码登录会话创建失败，请稍后重试")

        self.client_id = str(response["client_id"])
        self.request_id = str(response["request_id"])
        return QrChallenge(
            client_id=self.client_id,
            request_id=self.request_id,
            challenge_url=response["challenge_url"],
            interval=float(response["interval"]),
        )

    async def poll(self) -> QrPollResult:
        """轮询一次授权状态：未确认返回等待态，已确认返回凭据。"""
        if not self.client_id or not self.request_id:
            raise ValueError("登录会话已失效，请重新发起登录")

        resp = await request_ok_response(
            self.client,
            "POST",
            f"{self.api_base_url}{AUTH_POLL_STATUS}",
            tag=_TAG,
            data={"client_id": self.client_id, "request_id": self.request_id},
            timeout=self.timeout,
        )
        payload: QrPollResponse = resp.json()
        response = payload["response"]

        if "new_challenge_url" in response:
            # 手机端扫码后服务端会下发新链接，但原 client_id 仍能轮询到令牌
            logger.debug(f"[Steam·{_TAG}] 服务端轮换了二维码，继续用原会话轮询")

        scanned = bool(response["had_remote_interaction"]) if "had_remote_interaction" in response else False
        if "refresh_token" not in response or "access_token" not in response:
            return QrWaiting(done=False, scanned=scanned)

        access_token = response["access_token"]
        return QrReady(
            done=True,
            steamid64=steamid_from_access_token(access_token),
            account_name=response["account_name"] if "account_name" in response else "",
            access_token=access_token,
            refresh_token=response["refresh_token"],
        )
