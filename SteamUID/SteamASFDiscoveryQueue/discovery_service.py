from __future__ import annotations

from gsuid_core.models import Event

from ..SteamASFFarm.farm_service import get_user_asf_target
from ..SteamASFLogin.asf_client import ASFClient
from ..SteamConfig import SteamConfig
from ..utils.exceptions import SteamError
from ..utils.utils import maybe_hide_steamid


async def run_discovery_queue(ev: Event, text: str = "") -> str:
    """
    执行 ASF 队列探索，并在执行完毕后发送通知
    """
    asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
    if not asf_url:
        raise SteamError("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")

    bot_name, steamid64, is_asf_bound = await get_user_asf_target(ev, text)
    bot_info = await ASFClient.get_bot(bot_name)
    
    if not bot_info:
        if not is_asf_bound:
            raise SteamError("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
        else:
            raise SteamError("未在 ASF 中找到您的账号实例，请先使用【asf登录】重新登录！")

    # 发送 ASFEnhance 探索指令
    ok, raw_res = await ASFClient.send_command(f"ex {bot_name}", timeout=45.0)
    if not ok:
        raise SteamError(f"探索队列执行失败：{raw_res}")

    account_disp = maybe_hide_steamid(steamid64) if steamid64 else bot_name
    return (
        f"【Steam 探索队列】\n"
        f"账号：{account_disp}\n"
        f"状态：探索队列浏览完毕"
    )
