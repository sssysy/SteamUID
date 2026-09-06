# -*- coding: utf-8 -*-
import json
import os
import time
from base64 import b64encode
from binascii import hexlify
from typing import Any, Optional, Dict, List
import requests

from Cryptodome.Cipher import PKCS1_v1_5
from Cryptodome.PublicKey.RSA import construct as rsa_construct
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig

# 默认浏览器 User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/143.0.0.0 Safari/537.36"
)

STEAM_DOMAINS = [
    "store.steampowered.com",
    "help.steampowered.com",
    "steamcommunity.com",
]


class SteamAuthError(Exception):
    """Steam 认证基类异常"""
    pass


class LoginIncorrect(SteamAuthError):
    """账号或密码错误"""
    pass


class TwoFactorAuthRequired(SteamAuthError):
    """需要两步验证"""
    pass


class AuthCodeInvalid(SteamAuthError):
    """两步验证码无效或已过期"""
    pass


def rsa_encrypt_password(publickey_mod: str, publickey_exp: str, password: str) -> str:
    """使用 Steam 返回的 RSA 公钥加密账号密码"""
    key = rsa_construct((int(publickey_mod, 16), int(publickey_exp, 16)))
    return b64encode(PKCS1_v1_5.new(key).encrypt(password.encode("utf-8"))).decode("ascii")


def generate_session_id() -> str:
    """生成 24 位 16 进制字符串作为 sessionid"""
    return hexlify(os.urandom(12)).decode("ascii")


class SteamWebAuth:
    """
    Steam Web 授权核心认证器
    对接官方 IAuthenticationService API (基于 steam-next 规范)
    """

    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password

        self.client_id: Optional[str] = None
        self.request_id: Optional[str] = None
        self.steam_id: Optional[str] = None
        self.allowed_confirmations: List[int] = []
        self.refresh_token: Optional[str] = None
        self.access_token: Optional[str] = None
        self.session_id: Optional[str] = None
        self.logged_on: bool = False

        self.session = requests.Session()
        self.session.headers.update({
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/",
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": DEFAULT_USER_AGENT,
        })

        # 挂载代理
        self._apply_proxy()

    def _apply_proxy(self):
        try:
            proxy = SteamConfig.get_config("HttpProxy").data.strip()
            if proxy:
                self.session.proxies.update({"http": proxy, "https": proxy})
        except Exception:
            pass

    def _send_api_request(
        self,
        interface: str,
        method: str,
        version: int = 1,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        is_get: bool = False,
    ) -> dict:
        url = f"https://api.steampowered.com/{interface}/{method}/v{version}"
        try:
            if is_get:
                resp = self.session.get(url, params=params, timeout=12)
            else:
                resp = self.session.post(url, data=data, timeout=12)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"[SteamWebAuth] API 请求失败 [{url}]: {e}")
            raise SteamAuthError(f"连接 Steam API 异常: {e}")

    def _get_rsa_key(self) -> dict:
        """从 Steam 获取当前用户的 RSA 公钥与加密时间戳"""
        res = self._send_api_request(
            interface="IAuthenticationService",
            method="GetPasswordRSAPublicKey",
            version=1,
            params={"account_name": self.username},
            is_get=True,
        )
        response_body = res.get("response", {})
        if not response_body.get("publickey_mod") or not response_body.get("publickey_exp"):
            raise LoginIncorrect("无法获取密码加密密钥，请检查账号名是否输入正确")
        return response_body

    def start_session(self, username: str = "", password: str = "") -> dict:
        """
        发起初次认证会话
        返回 dict:
            {"ok": True, "need_2fa": False, "done": True, "steamid64": "..."}
            或
            {"ok": True, "need_2fa": True, "can_app_confirm": True/False, "hint": "..."}
        """
        self.username = username or self.username
        self.password = password or self.password

        if not self.username or not self.password:
            raise LoginIncorrect("账号名或密码不能为空")

        # 1. 获取公钥并加密密码
        rsa_info = self._get_rsa_key()
        encrypted_pwd = rsa_encrypt_password(
            rsa_info["publickey_mod"],
            rsa_info["publickey_exp"],
            self.password,
        )
        timestamp = rsa_info["timestamp"]

        # 2. 调用 BeginAuthSessionViaCredentials 发起凭据会话
        data = {
            "device_friendly_name": DEFAULT_USER_AGENT,
            "account_name": self.username,
            "encrypted_password": encrypted_pwd,
            "encryption_timestamp": str(timestamp),
            "remember_login": "1",
            "platform_type": "2",  # Web 浏览器平台
            "persistence": "1",
            "website_id": "Community",
        }

        resp = self._send_api_request(
            interface="IAuthenticationService",
            method="BeginAuthSessionViaCredentials",
            version=1,
            data=data,
        )

        response = resp.get("response", {})
        if not response.get("client_id") or not response.get("request_id"):
            raise LoginIncorrect("账号或密码错误，请重新输入")

        self.client_id = str(response["client_id"])
        self.request_id = str(response["request_id"])
        self.steam_id = str(response.get("steamid", ""))

        # 提取支持的两步验证类型
        # 1: EmailCode, 2: DeviceCode, 3: DeviceConfirmation (手机 App 确认)
        confirmations = response.get("allowed_confirmations", [])
        self.allowed_confirmations = [c.get("confirmation_type") for c in confirmations if "confirmation_type" in c]

        can_app_confirm = 3 in self.allowed_confirmations
        using_email = 1 in self.allowed_confirmations

        # 3. 尝试直接轮询（如果用户账号无 2FA 则直接完成）
        try:
            self._poll_status()
            self._finalize_login()
            return {
                "ok": True,
                "done": True,
                "need_2fa": False,
                "steamid64": self.steam_id,
            }
        except TwoFactorAuthRequired:
            # 需要 2FA
            if using_email:
                hint = "请输入发送至您绑定邮箱的验证码"
            elif can_app_confirm:
                hint = "请在 Steam App 中确认登录，或在下方输入 5 位动态令牌"
            else:
                hint = "请输入手机 Steam 应用中的 5 位动态令牌码"

            return {
                "ok": True,
                "done": False,
                "need_2fa": True,
                "can_app_confirm": can_app_confirm,
                "hint": hint,
            }

    def _poll_status(self):
        """轮询验证会话状态"""
        if not self.client_id or not self.request_id:
            raise SteamAuthError("尚未初始化登录会话")

        data = {
            "client_id": self.client_id,
            "request_id": self.request_id,
        }

        resp = self._send_api_request(
            interface="IAuthenticationService",
            method="PollAuthSessionStatus",
            version=1,
            data=data,
        )

        response = resp.get("response", {})
        self.refresh_token = response.get("refresh_token")
        self.access_token = response.get("access_token")

        if not self.refresh_token or not self.access_token:
            raise TwoFactorAuthRequired("需要完成两步验证")

    def submit_2fa_code(self, code: str) -> dict:
        """提交 2FA 动态令牌或邮箱验证码"""
        if not self.client_id or not self.steam_id:
            raise SteamAuthError("登录会话已失效，请重新发起登录")

        code = code.strip().upper()
        if not code:
            raise AuthCodeInvalid("验证码不能为空")

        # 判断类型：如果包含 EmailCode 且不包含 DeviceCode，则 code_type = 1
        code_type = 1 if (1 in self.allowed_confirmations and 2 not in self.allowed_confirmations) else 2

        data = {
            "client_id": self.client_id,
            "steamid": self.steam_id,
            "code": code,
            "code_type": str(code_type),
        }

        try:
            self._send_api_request(
                interface="IAuthenticationService",
                method="UpdateAuthSessionWithSteamGuardCode",
                version=1,
                data=data,
            )
        except Exception as e:
            logger.warning(f"[SteamWebAuth] 提交令牌返回错误: {e}")
            raise AuthCodeInvalid("两步验证码错误或已失效，请重新输入")

        # 提交后轮询状态
        try:
            self._poll_status()
        except TwoFactorAuthRequired:
            raise AuthCodeInvalid("两步验证码验证未通过，请重新输入")

        self._finalize_login()
        return {
            "ok": True,
            "done": True,
            "steamid64": self.steam_id,
        }

    def check_app_confirmation(self) -> dict:
        """检查用户是否已在手机 Steam App 上点击了允许/确认"""
        if not self.client_id or not self.request_id:
            raise SteamAuthError("登录会话已失效，请重新发起登录")

        try:
            self._poll_status()
            self._finalize_login()
            return {
                "ok": True,
                "done": True,
                "steamid64": self.steam_id,
            }
        except TwoFactorAuthRequired:
            return {
                "ok": False,
                "done": False,
                "msg": "尚未检测到手机端确认，请在手机 App 上点击【允许】",
            }

    def _finalize_login(self):
        """登录成功，组装并写入所有 Cookie 凭证"""
        self.session_id = generate_session_id()
        self.logged_on = True

        for domain in STEAM_DOMAINS:
            self.session.cookies.set("sessionid", self.session_id, domain=domain)
            self.session.cookies.set(
                "steamLoginSecure",
                f"{self.steam_id}||{self.access_token}",
                domain=domain,
                secure=True,
            )

    def get_credentials(self) -> dict:
        """获取结构化的凭据字典，供写入数据库持久化"""
        cookies_dict = {}
        for cookie in self.session.cookies:
            cookies_dict[cookie.name] = cookie.value

        return {
            "steamid64": self.steam_id,
            "account_name": self.username,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "session_id": self.session_id,
            "cookies": cookies_dict,
        }
