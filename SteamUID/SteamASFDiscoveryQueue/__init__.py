from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamASFFarm.farm_service import get_user_asf_target
from ..SteamASFLogin.asf_client import ASFClient
from ..SteamConfig import SteamConfig
from ..utils.database.models import SteamBind
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import auto2steamid64, maybe_hide_steamid

discovery_sv = SV("ASF探索队列")


async def _switch_auto_discovery(ev: Event, enabled: bool) -> str:
    """切换自动探索队列开关"""
    text = ev.text.strip()
    target_sid = auto2steamid64(text) or (text if text.isdigit() else None)
    subs = await SteamBind.get_binds_by_user(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )
    if not subs:
        raise SteamValidationError("你没有绑定任何账号，无法修改自动探索设置！")

    if target_sid:
        target_binds = [s for s in subs if s.steamid64 == target_sid]
        if not target_binds:
            raise SteamValidationError("你没有绑定该 steamid，无法修改自动探索设置！")
    else:
        target_binds = subs

    error_ids = set()
    for sub in target_binds:
        status = await SteamBind.set_push_status(
            sub.steamid64,
            ev.bot_id,
            ev.user_id,
            ev.user_type,
            "auto_discovery_queue",
            enabled,
            ev.group_id,
        )
        if status != 0:
            error_ids.add(sub.steamid64)

    if error_ids:
        failed_ids = "\n".join(maybe_hide_steamid(sid) for sid in error_ids)
        return f"{failed_ids}\n自动探索队列状态切换失败"

    action_str = "开启" if enabled else "关闭"
    if len(target_binds) == 1:
        sid_disp = maybe_hide_steamid(target_binds[0].steamid64)
        return f"账号【{sid_disp}】已成功{action_str}每日自动探索队列任务！"
    else:
        return f"已成功为所有已绑定账号{action_str}每日自动探索队列任务！"


@discovery_sv.on_command(("开启自动探索", "开启自动探索队列"))
async def enable_auto_discovery_queue(bot: Bot, ev: Event):
    try:
        res = await _switch_auto_discovery(ev, True)
        await bot.send(res)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFDiscoveryQueue] 开启自动探索命令异常: {e!r}")
        await bot.send("开启自动探索失败，详情请查看后台。")


@discovery_sv.on_command(("关闭自动探索", "关闭自动探索队列"))
async def disable_auto_discovery_queue(bot: Bot, ev: Event):
    try:
        res = await _switch_auto_discovery(ev, False)
        await bot.send(res)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFDiscoveryQueue] 关闭自动探索命令异常: {e!r}")
        await bot.send("关闭自动探索失败，详情请查看后台。")


@discovery_sv.on_command(("自动探索状态", "自动探索队列状态"))
async def check_auto_discovery_status(bot: Bot, ev: Event):
    try:
        binds = await SteamBind.get_binds_by_user(
            ev.bot_id, ev.user_id, ev.user_type, ev.group_id
        )
        if not binds:
            await bot.send("你尚未绑定任何 Steam 账号！")
            return

        msg_lines = ["【Steam 自动探索队列状态】"]
        for b in binds:
            steamid_disp = maybe_hide_steamid(b.steamid64) if b.steamid64 else b.user_id
            status_str = "开启" if b.auto_discovery_queue else "关闭"
            msg_lines.append(f"账号：{steamid_disp} -> 自动探索：{status_str}")
        await bot.send("\n".join(msg_lines))
    except Exception as e:
        logger.exception(f"[SteamASFDiscoveryQueue] 查询自动探索状态异常: {e!r}")
        await bot.send("查询自动探索状态失败，详情请查看后台。")


@discovery_sv.on_command("探索队列")
async def steamasf_discovery_queue(bot: Bot, ev: Event):
    """通过 ASF (ASFEnhance) 立即执行单次 Steam 探索队列"""
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
