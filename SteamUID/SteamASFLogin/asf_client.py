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
    async def delete_bot(cls, bot_name: str) -> bool:
        """从 ASF 中停止并删除 Bot 实例"""
        url = f"{cls._base_url()}/Api/Bot/{bot_name}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.delete(url, headers=cls._headers())
                if resp.status_code == 200:
                    return True
                logger.warning(f"[SteamASF] 删除 Bot {bot_name} 返回状态码: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"[SteamASF] 删除 Bot {bot_name} 请求失败: {e!r}")
        return False

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
            "GamesPlayedWhileIdle": [],
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
    async def start_bot(cls, bot_name: str) -> bool:
        """启动 ASF Bot 实例"""
        url = f"{cls._base_url()}/Api/Bot/{bot_name}/Start"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, headers=cls._headers())
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"[SteamASF] 启动 Bot {bot_name} 请求失败: {e!r}")
            return False

    @classmethod
    async def send_command(cls, command: str, timeout: float = 10.0) -> tuple[bool, str]:
        """向 ASF IPC 发送控制命令并返回响应结果"""
        url = f"{cls._base_url()}/Api/Command"
        payload = {"Command": command}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=cls._headers(), json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    res = data.get("Result", "")
                    return True, str(res).strip()
                return False, f"ASF 返回错误码: {resp.status_code}"
        except Exception as e:
            logger.error(f"[SteamASF] 发送 ASF 命令 `{command}` 失败: {e!r}")
            return False, f"请求失败: {e}"

    @classmethod
    async def resume_farming(cls, bot_name: str) -> tuple[bool, str]:
        """恢复/开始挂卡任务"""
        return await cls.send_command(f"resume {bot_name}")

    @classmethod
    async def pause_farming(cls, bot_name: str) -> tuple[bool, str]:
        """暂停/停止挂卡任务"""
        return await cls.send_command(f"pause {bot_name}")

    @classmethod
    async def set_persona_state(cls, bot_name: str, state: int | str = 7) -> tuple[bool, str]:
        """设置 Bot 的在线状态 (0=Offline, 1=Online, 7=Invisible 等)"""
        return await cls.send_command(f"persona {bot_name} {state}")

    @classmethod
    async def ensure_idle_and_invisible(cls, bot_name: str) -> None:
        """确保 Bot 处于暂停挂卡状态且保持隐身"""
        try:
            await cls.pause_farming(bot_name)
            await cls.set_persona_state(bot_name, 7)
        except Exception as e:
            logger.warning(f"[SteamASF] 确保 Bot {bot_name} 隐身并暂停挂卡失败: {e!r}")

    @classmethod
    async def check_bot_logged_in(cls, bot_name: str) -> tuple[bool, str]:
        """快速检查 Bot 是否已登录成功并返回 (是否成功, steamid64)"""
        bot_info = await cls.get_bot(bot_name)
        if bot_info:
            is_logged_in = bot_info.get("IsConnectedAndLoggedOn", False)
            s_steamid = str(bot_info.get("s_SteamID") or bot_info.get("SteamID") or "")
            if is_logged_in and s_steamid and s_steamid != "0":
                return True, s_steamid
        return False, ""

    @classmethod
    async def input_credential(
        cls, bot_name: str, input_type: str, value: str
    ) -> bool:
        """向 ASF Bot 提交 2FA 令牌 / 验证码凭据"""
        cmd = f"input {bot_name} {input_type} {value}"
        ok, res = await cls.send_command(cmd)
        if not ok:
            logger.warning(f"[SteamASF] 提交 2FA 凭据命令失败 bot={bot_name}: {res}")
            return False
        
        logger.info(f"[SteamASF] 已向 Bot {bot_name} 提交 2FA 凭据: {res}")
        return True

    @classmethod
    async def poll_bot_status(
        cls, bot_name: str, max_wait_seconds: float = 6.0
    ) -> dict[str, Any]:
        """
        初始账号密码登录时的状态轮询
        用于快速判断是直接登录成功，还是需要 2FA 验证
        """
        interval = 0.8
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
                elif req_input:
                    return {
                        "status": "need_2fa",
                        "input_type": "TwoFactorAuthentication",
                        "hint": "请输入 5 位 Steam 令牌码；若手机端已弹出登录确认，请在手机上点击【批准】后直接点击【确认验证】",
                    }

            await asyncio.sleep(interval)
            elapsed += interval

        return {
            "status": "pending",
            "msg": "正在等待 ASF 登录响应...",
        }

    @classmethod
    async def poll_bot_login(
        cls, bot_name: str, max_wait_seconds: float = 12.0
    ) -> dict[str, Any]:
        """
        提交 2FA 凭据或手机端批准后的专项登录轮询
        持续等待 Bot 建立连接并登录成功，不打断现有授权会话
        """
        interval = 0.8
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            is_logged_in, s_steamid = await cls.check_bot_logged_in(bot_name)
            if is_logged_in:
                return {
                    "status": "logged_in",
                    "steamid64": s_steamid,
                    "msg": "登录成功",
                }

            await asyncio.sleep(interval)
            elapsed += interval

        # 超时后再做一次最终状态判定
        is_logged_in, s_steamid = await cls.check_bot_logged_in(bot_name)
        if is_logged_in:
            return {
                "status": "logged_in",
                "steamid64": s_steamid,
                "msg": "登录成功",
            }

        return {
            "status": "failed",
            "msg": "登录等待超时",
        }
