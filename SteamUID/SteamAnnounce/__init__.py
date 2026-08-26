from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.subscribe import gs_subscribe

from ..utils.api import get_game_announcements, get_game_info
from ..utils.database.models import SteamAnnounceInfo
from ..utils.database.models_cache import SteamApiCache
from ..utils.exceptions import SteamError
from ..utils.render import render_game_announce
from ..utils.utils import resolve_target_appid
from ..SteamConfig.interface import SteamAPI
import json

announce_SV = SV("steam游戏公告订阅")

@announce_SV.on_command(("订阅公告查看", "订阅公告列表", "查看订阅公告"), block=True)
async def query_announce_subs(bot: Bot, ev: Event):
    try:
        sub_list = await gs_subscribe.get_subscribe(
            task_name="订阅steam游戏公告",
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
            WS_BOT_ID=ev.WS_BOT_ID,
        )

        if not sub_list:
            await bot.send("您当前没有订阅任何游戏公告。")
            return

        lines = ["[SteamUID] 当前已订阅的游戏公告:"]
        for sub in sub_list:
            aid = sub.uid
            if not aid:
                continue
            game_name = aid
            # 尝试从缓存读取游戏名
            cached = await SteamApiCache.get_cache(aid)
            if cached:
                try:
                    c_data = json.loads(cached)
                    name = c_data.get("data", {}).get("name") if isinstance(c_data, dict) else None
                    if name:
                        game_name = name
                except Exception:
                    pass
            lines.append(f"• {game_name} ({aid})")

        await bot.send("\n".join(lines))

    except Exception as e:
        logger.exception(f"[SteamAnnounce] 查询订阅列表异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")

@announce_SV.on_command("订阅公告")
async def subscribe_announce(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        # 尝试获取游戏基本信息
        game_name = appid
        try:
            game_data = await get_game_info(appid)
            if game_data and game_data.get("success"):
                game_name = game_data.get("data", {}).get("name", appid)
        except Exception as e:
            logger.warning(f"[SteamAnnounce] 获取游戏信息异常 appid={appid}: {e}")

        # 拉取当前最新公告作为基线，避免刚订阅就推送旧公告
        last_gid = ""
        last_time = 0
        try:
            latest_list = await get_game_announcements(appid, count=1)
            if latest_list:
                last_gid = latest_list[0].get("gid", "")
                last_time = latest_list[0].get("post_time", 0)
        except Exception as e:
            logger.warning(f"[SteamAnnounce] 初始化基线公告异常 appid={appid}: {e}")

        # 保存订阅基线
        await SteamAnnounceInfo.subscribe(
            appid=appid,
            last_gid=last_gid,
            last_time=last_time,
        )

        # 写入框架订阅管理
        await gs_subscribe.add_subscribe(
            subscribe_type="single",
            task_name="订阅steam游戏公告",
            event=ev,
            uid=appid,
        )

        await bot.send(
            f"已成功订阅【{game_name}】({appid})的游戏公告！\n当游戏有新公告发布时将会提醒您。"
        )

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamAnnounce] 订阅公告命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")


@announce_SV.on_command("取消订阅公告")
async def unsubscribe_announce(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        # 删除框架订阅
        await gs_subscribe.delete_subscribe(
            subscribe_type="single",
            task_name="订阅steam游戏公告",
            event=ev,
            uid=appid,
            WS_BOT_ID=ev.WS_BOT_ID,
        )

        # 检查是否已无其他订阅者
        status = await gs_subscribe.get_subscribe(
            task_name="订阅steam游戏公告",
            uid=appid,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
        )

        if not status:
            await SteamAnnounceInfo.unsubscribe(appid)

        await bot.send(f"您已成功取消订阅 {appid} 的游戏公告！")

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamAnnounce] 取消订阅公告命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")


@announce_SV.on_command("测试订阅公告")
async def test_announce_push(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        # 获取游戏信息
        game_name = appid
        game_logo_url = SteamAPI.GetGameCoverImageURL(appid, "header")
        try:
            game_data = await get_game_info(appid)
            if game_data and game_data.get("success"):
                d = game_data.get("data", {})
                game_name = d.get("name", appid)
                game_logo_url = d.get("header_image") or game_logo_url
        except Exception as e:
            logger.warning(f"[SteamAnnounce] 测试命令拉取游戏详情异常 appid={appid}: {e}")

        # 拉取最新公告
        announcements = await get_game_announcements(appid, count=1)
        if not announcements:
            await bot.send(f"未获取到【{game_name}】({appid})的任何公告记录！")
            return

        latest_item = announcements[0]

        # 渲染公告卡片
        img_bytes = await render_game_announce(
            announce_item=latest_item,
            appid=appid,
            game_name=game_name,
            game_logo_url=game_logo_url,
        )

        send_msg = [
            MessageSegment.at(ev.user_id),
            MessageSegment.text(f"\n[Steam 公告订阅]{game_name} 发布了新公告\n"),
            MessageSegment.image(img_bytes),
            MessageSegment.text(f"公告链接: {latest_item['url']}"),
        ]
        await bot.send(send_msg)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamAnnounce] 测试订阅公告命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")
