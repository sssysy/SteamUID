from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamASFFarm.farm_service import get_user_asf_target
from ..SteamASFLogin.asf_client import ASFClient
from ..SteamConfig import SteamConfig
from ..utils.exceptions import SteamError
from ..utils.utils import maybe_hide_steamid

discovery_sv = SV("ASF探索队列")


@discovery_sv.on_command("探索队列")
async def steamasf_discovery_queue(bot: Bot, ev: Event):
    """通过 ASF (ASFEnhance) 自动执行 Steam 探索队列"""
    try:
        asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
        if not asf_url:
            await bot.send("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")
            return

        bot_name, steamid64, is_asf_bound = await get_user_asf_target(ev, ev.text)
        bot_info = await ASFClient.get_bot(bot_name)

        if not bot_info:
            if not is_asf_bound:
                await bot.send("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
            else:
                await bot.send("未在 ASF 中找到您的账号实例，请先使用【asf登录】重新登录！")
            return

        # 发送 ASFEnhance 探索指令
        ok, raw_res = await ASFClient.send_command(f"ex {bot_name}", timeout=45.0)
        if not ok:
            await bot.send(f"探索队列执行失败：{raw_res}")
            return

        account_disp = maybe_hide_steamid(steamid64) if steamid64 else bot_name
        await bot.send(
            f"【Steam 探索队列】\n"
            f"账号：{account_disp}\n"
            f"状态：探索队列浏览完毕"
        )
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFDiscoveryQueue] 探索队列命令异常: {e!r}")
        await bot.send("探索队列发生未知错误，详情请查看后台。")
