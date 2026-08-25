import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..SteamASFLogin.asf_client import ASFClient
from ..SteamConfig import SteamConfig
from ..utils.exceptions import SteamError
from ..utils.utils import maybe_hide_steamid
from . import farm_service

farm_sv = SV("ASF挂卡")


@farm_sv.on_command(("开始挂卡",))
async def steamasf_start_farming(bot: Bot, ev: Event):
    """启动/恢复 ASF 挂卡任务"""
    try:
        asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
        if not asf_url:
            await bot.send("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")
            return

        bot_name, steamid64, is_asf_bound = await farm_service.get_user_asf_target(ev, ev.text)
        bot_info = await ASFClient.get_bot(bot_name)

        if not bot_info:
            if not is_asf_bound:
                await bot.send("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
            else:
                await bot.send("未在 ASF 中找到您的账号实例，请先使用【asf登录】重新登录！")
            return

        is_connected = bot_info.get("IsConnectedAndLoggedOn", False)
        if not is_connected:
            await ASFClient.start_bot(bot_name)
            await asyncio.sleep(1.0)

        # 发送 resume 挂卡指令
        ok, res_msg = await ASFClient.resume_farming(bot_name)
        if not ok:
            await bot.send(f"开始挂卡失败：{res_msg}")
            return

        # 等待片刻让 ASF 刷新 CardsFarmer 进度数据
        await asyncio.sleep(0.8)
        updated_bot_info = await ASFClient.get_bot(bot_name)

        if updated_bot_info:
            data = farm_service.parse_farming_data(updated_bot_info)
            total_games = data["total_games_count"]
            total_cards = data["total_cards_count"]
            time_formatted = data["formatted_time"]
            current_games = data["current_games"]

            if total_games > 0:
                lines = [
                    "已开始挂卡！",
                    f"剩余挂卡游戏：{total_games} 个（共 {total_cards} 张卡片）",
                    f"预计剩余时间：{time_formatted}",
                ]
                if current_games:
                    curr_list = []
                    for g in current_games[:3]:
                        g_name = g.get("GameName") or f"AppID {g.get('AppID')}"
                        c_rem = g.get("CardsRemaining") or 0
                        curr_list.append(f"{g_name} (剩 {c_rem} 张)")
                    lines.append(f"当前正在挂卡：{', '.join(curr_list)}")
                await bot.send("\n".join(lines))
                return
            else:
                await bot.send("已开始挂卡！\n当前暂无需要挂卡的游戏，所有卡片已全部收集完毕。")
                return

        await bot.send("已向 ASF 发送开始挂卡指令！可通过【steam挂卡状态】查看挂卡进度。")
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFFarm] 开始挂卡命令异常: {e!r}")
        await bot.send("开始挂卡发生未知错误，详情请查看后台。")


@farm_sv.on_command(("结束挂卡", "停止挂卡"))
async def steamasf_stop_farming(bot: Bot, ev: Event):
    """停止/暂停 ASF 挂卡任务"""
    try:
        asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
        if not asf_url:
            await bot.send("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")
            return

        bot_name, steamid64, is_asf_bound = await farm_service.get_user_asf_target(ev, ev.text)
        bot_info = await ASFClient.get_bot(bot_name)

        if not bot_info:
            if not is_asf_bound:
                await bot.send("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
            else:
                await bot.send("未在 ASF 中找到您的账号实例，请先使用【asf登录】重新登录！")
            return

        ok, res_msg = await ASFClient.pause_farming(bot_name)
        if ok:
            await bot.send(
                "已结束/暂停挂卡！\n"
                "如需继续挂卡可发送【steam开始挂卡】，查询进度可发送【steam挂卡状态】。"
            )
        else:
            await bot.send(f"暂停挂卡失败：{res_msg}")
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFFarm] 结束挂卡命令异常: {e!r}")
        await bot.send("结束挂卡发生未知错误，详情请查看后台。")


@farm_sv.on_command(("挂卡状态", "挂卡进度"))
async def steamasf_farming_status(bot: Bot, ev: Event):
    """查询 ASF 挂卡状态与进度"""
    try:
        asf_url = SteamConfig.get_config("steamasfbaseurl").data.strip()
        if not asf_url:
            await bot.send("未配置 ASF IPC 地址 (steamasfbaseurl)，请管理员在 SteamConfig 中进行配置！")
            return

        bot_name, steamid64, is_asf_bound = await farm_service.get_user_asf_target(ev, ev.text)
        bot_info = await ASFClient.get_bot(bot_name)

        if not bot_info:
            if not is_asf_bound:
                await bot.send("您尚未通过 ASF 绑定 Steam 账号，请先使用【asf登录】绑定账号！")
            else:
                await bot.send("未在 ASF 中找到您的账号，请确认 ASF 服务已正常运行且账号已登录。")
            return

        is_connected = bot_info.get("IsConnectedAndLoggedOn", False)
        if not is_connected:
            await bot.send("ASF 账号当前处于离线/未连接状态，无法获取挂卡进度。")
            return

        data = farm_service.parse_farming_data(bot_info)
        paused = data["paused"]
        total_games = data["total_games_count"]
        total_cards = data["total_cards_count"]
        time_formatted = data["formatted_time"]
        current_games = data["current_games"]
        games_to_farm = data["games_to_farm"]

        # 状态文本判定
        if paused:
            status_text = "已暂停挂卡"
        elif total_games > 0:
            status_text = "正在挂卡"
        else:
            status_text = "已完成 (无待挂卡游戏)"

        account_disp = maybe_hide_steamid(steamid64) if steamid64 else bot_name
        lines = [
            "【Steam 挂卡状态】",
            f"账号：{account_disp}",
            f"挂卡状态：{status_text}",
            f"剩余挂卡游戏：{total_games} 个（共 {total_cards} 张卡片）",
            f"预计剩余时间：{time_formatted}",
        ]

        if current_games:
            lines.append("\n当前正在挂卡：")
            for g in current_games:
                g_name = g.get("GameName") or f"AppID {g.get('AppID')}"
                g_id = g.get("AppID")
                c_rem = g.get("CardsRemaining") or 0
                lines.append(f"- {g_name} (AppID: {g_id}，剩余 {c_rem} 张)")

        # 队列中等待挂卡的游戏（过滤掉正在挂的，展示前5个）
        current_appids = {g.get("AppID") for g in current_games if g.get("AppID")}
        waiting_games = [g for g in games_to_farm if g.get("AppID") not in current_appids]
        if waiting_games:
            lines.append("\n等待挂卡队列（前5个）：")
            for i, g in enumerate(waiting_games[:5], 1):
                g_name = g.get("GameName") or f"AppID {g.get('AppID')}"
                c_rem = g.get("CardsRemaining") or 0
                lines.append(f"{i}. {g_name} (剩 {c_rem} 张)")
            if len(waiting_games) > 5:
                lines.append(f"... 还有 {len(waiting_games) - 5} 个游戏在队列中")

        if paused and total_games > 0:
            lines.append("\n💡 提示：挂卡当前已暂停，可发送【steam开始挂卡】继续挂卡。")
        elif not paused and total_games == 0:
            lines.append("\n✨ 提示：所有拥有卡片掉落的游戏已全部挂完！")

        await bot.send("\n".join(lines))
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamASFFarm] 挂卡状态命令异常: {e!r}")
        await bot.send("查询挂卡状态发生未知错误，详情请查看后台。")
