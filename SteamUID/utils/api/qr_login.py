"""Steam 扫码登录协议（IAuthenticationService QR 流程）。

只推进 BeginAuthSessionViaQR / PollAuthSessionStatus 两个接口与令牌获取，
凭据落库 / 会话校验由调用方处理。
"""

import base64
from types import TracebackType

from gsuid_core.logger import logger

from .auth import steamid_from_access_token
from .client import MOBILE_API_HEADERS, make_async_client, request_ok_response
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
)

_TAG = "扫码登录"

# EAuthTokenPlatformType_MobileApp = 3，配 Android 设备信息；手机 App 只认这种二维码
_PLATFORM_TYPE = 3
_OS_TYPE = -500
_GAMING_DEVICE_TYPE = 528
# 会显示在用户的 Steam 授权设备列表里
_DEVICE_NAME = "GsCore_SteamUID"


def _varint(value: int) -> bytes:
    """protobuf varint；负数按 64 位补码写，os_type=-500 就是这种编码。"""
    value &= (1 << 64) - 1
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _field_varint(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _field_string(field: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return _varint((field << 3) | 2) + _varint(len(raw)) + raw


def _qr_request_payload(device_name: str) -> str:
    """把 CAuthentication_BeginAuthSessionViaQR_Request 编成 base64（device_details 是第 3 字段）。"""
    details = _field_string(1, device_name)
    details += _field_varint(2, _PLATFORM_TYPE)
    details += _field_varint(3, _OS_TYPE)
    details += _field_varint(4, _GAMING_DEVICE_TYPE)
    request = _varint((3 << 3) | 2) + _varint(len(details)) + details
    return base64.b64encode(request).decode("ascii")


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
            headers=MOBILE_API_HEADERS,
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
            params={"format": "json"},
            files={"input_protobuf_encoded": (None, _qr_request_payload(_DEVICE_NAME))},
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
            # 轮换出来的新二维码扫不了，原 client_id 照样能收到确认，忽略新链接即可
            logger.debug(f"[Steam·{_TAG}] 服务端轮换了二维码（新码不可用），继续用原会话轮询")

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
