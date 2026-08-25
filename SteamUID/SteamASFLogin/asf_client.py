from __future__ import annotations

import asyncio
from typing import Any
import httpx

from gsuid_core.logger import logger
from ..SteamConfig import SteamConfig


class ASFClient:
    """ASF (ArchiSteamFarm) IPC 客户端封装"""

    @classmethod
    def _base_url(cls) -> str:
        url = SteamConfig.get_config("steamasfbaseurl").data.strip()
        if not url:
            return "http://127.0.0.1:1242"
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"http://{url}"
        return url.rstrip("/")

    @classmethod
    def _headers(cls) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = SteamConfig.get_config("steamasfipckey").data.strip()
        if key:
            headers["Authentication"] = key
        return headers

    @classmethod
    async def is_available(cls) -> bool:
        """检查 ASF IPC 服务是否可用"""
        url = f"{cls._base_url()}/Api/ASF"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, headers=cls._headers())
                return resp.status_code == 200
        except Exception:
            return False

    @classmethod
    async def get_bot(cls, bot_name: str) -> dict[str, Any] | None:
        """获取单个 Bot 信息"""
        url = f"{cls._base_url()}/Api/Bot/{bot_name}"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=cls._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    res = data.get("Result", {})
                    if isinstance(res, dict) and bot_name in res:
                        return res[bot_name]
                    return res
        except Exception as e:
            logger.warning(f"[SteamASF] 获取 Bot {bot_name} 状态失败: {e!r}")
        return None

    @classmethod
    async def create_or_update_bot(
        cls, bot_name: str, steam_login: str, steam_password: str
    ) -> bool:
        """在 ASF 中创建或更新 Bot 配置并启动"""
        url = f"{cls._base_url()}/Api/Bot/{bot_name}"
        bot_config = {
            "SteamLogin": steam_login,
            "SteamPassword": steam_password,
            "Enabled": True,
            "Paused": True,
            "OnlineStatus": 7,
        }
        payload = {"BotConfig": bot_config}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                # 尝试创建
                resp = await client.post(url, headers=cls._headers(), json=payload)
                if resp.status_code == 200:
                    return True
                # 若已存在则尝试更新
                resp = await client.put(url, headers=cls._headers(), json=payload)
                if resp.status_code == 200:
                    # 尝试启动 Bot
                    start_url = f"{cls._base_url()}/Api/Bot/{bot_name}/Start"
                    await client.post(start_url, headers=cls._headers())
                    return True
                logger.warning(f"[SteamASF] 创建/更新 Bot {bot_name} 返回错误: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"[SteamASF] 创建/更新 Bot {bot_name} 请求失败: {e!r}")
        return False

    @classmethod
    async def input_credential(
        cls, bot_name: str, input_type: str, value: str
    ) -> bool:
        """向 ASF Bot 提交 2FA 令牌 / 验证码凭据"""
        url = f"{cls._base_url()}/Api/Bot/{bot_name}/Input"
        payload = {
            "Type": input_type,
            "Value": value,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, headers=cls._headers(), json=payload)
                if resp.status_code == 200:
                    return True
                # 回退方案：通过 ASF Command 接口提交 input 命令
                cmd_url = f"{cls._base_url()}/Api/Command"
                cmd_payload = {"Command": f"input {bot_name} {input_type} {value}"}
                resp_cmd = await client.post(cmd_url, headers=cls._headers(), json=cmd_payload)
                return resp_cmd.status_code == 200
        except Exception as e:
            logger.error(f"[SteamASF] 提交 2FA 凭据失败 bot={bot_name}: {e!r}")
        return False

    @classmethod
    async def poll_bot_status(
        cls, bot_name: str, max_wait_seconds: float = 6.0
    ) -> dict[str, Any]:
        """
        轮询 ASF Bot 的鉴权登录状态
        返回状态字典:
          - status: "logged_in" | "need_2fa" | "failed" | "pending"
          - steamid64: str
          - input_type: str ("TwoFactorAuthentication" | "SteamGuard")
          - msg: str
        """
        interval = 1.0
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            bot_info = await cls.get_bot(bot_name)
            if bot_info:
                is_logged_in = bot_info.get("IsConnectedAndLoggedOn", False)
                s_steamid = str(bot_info.get("s_SteamID") or bot_info.get("SteamID") or "")
                if is_logged_in and s_steamid and s_steamid != "0":
                    return {
                        "status": "logged_in",
                        "steamid64": s_steamid,
                        "msg": "登录成功",
                    }

                req_input = bot_info.get("RequiredInput")
                # RequiredInput: 1 (SteamGuard), 2 (TwoFactorAuthentication), 3 (SteamParentalCode), 4 (Password), etc.
                if req_input in (1, "SteamGuard", "1"):
                    return {
                        "status": "need_2fa",
                        "input_type": "SteamGuard",
                        "hint": "请输入发送至您邮箱的 SteamGuard 验证码",
                    }
                elif req_input in (2, "TwoFactorAuthentication", "2"):
                    return {
                        "status": "need_2fa",
                        "input_type": "TwoFactorAuthentication",
                        "hint": "请输入您的 Steam 手机令牌验证码",
                    }
                elif req_input:
                    return {
                        "status": "need_2fa",
                        "input_type": "TwoFactorAuthentication",
                        "hint": "请输入您的 Steam 令牌验证码",
                    }

            await asyncio.sleep(interval)
            elapsed += interval

        return {
            "status": "pending",
            "msg": "正在等待 ASF 登录响应...",
        }
