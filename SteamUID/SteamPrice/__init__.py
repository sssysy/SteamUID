from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.subscribe import gs_subscribe

from ..utils.database.models import SteamPriceInfo
from ..utils.api import get_game_info, get_price_data
from ..utils.exceptions import SteamError
from ..utils.render import render_game_price_drop
from ..utils.utils import resolve_target_appid
from ..SteamConfig import SteamConfig, get_current_region
from ..SteamConfig.interface import SteamAPI
import json



price_SV = SV("steam商店降价提醒")

@price_SV.on_command("订阅降价")
async def steamsubscribe(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        region = get_current_region()
        first_prices = await get_price_data(appid)
        if not first_prices.get(appid, {}).get("success", False):
            await bot.send(f"订阅失败！\n原因: 获取该游戏价格失败！请确认该 appid 在 {region.name}({region.cc}) 区是否锁区！")
            return

        if not first_prices.get(appid, {}).get("data", []):
            await bot.send(f"该游戏为免费游戏，无法订阅降价提醒")
            return

        await SteamPriceInfo.subscribe(appid, json.dumps(first_prices.get(appid, {}).get("data", {}).get("price_overview", {})))
        await gs_subscribe.add_subscribe(
            subscribe_type="single", 
            task_name="steam商店降价订阅", 
            event=ev, 
            uid=appid
            )
        await bot.send(f"已订阅 {appid}, 将在游戏降价时通知您！")
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamPrice] 订阅命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")

@price_SV.on_command("取消订阅降价")
async def steam_unsubscribe(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        await gs_subscribe.delete_subscribe(subscribe_type="single", task_name="steam商店降价订阅", event=ev, uid=appid, WS_BOT_ID=ev.WS_BOT_ID)

        status = await gs_subscribe.get_subscribe(
            task_name="steam商店降价订阅", 
            uid=appid,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
        )

        if not status:
            if await SteamPriceInfo.unsubscribe(appid) == -1:
                await bot.send(f"取消订阅失败！\n原因: 未找到该 appid 的相关订阅！")
                return

        await bot.send(f"您取消订阅 {appid} 成功！")

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamPrice] 取消订阅命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")

@price_SV.on_command(("订阅降价查看", "订阅降价列表"))
async def steam_query(bot: Bot, ev: Event):
    try:
        price_info = await gs_subscribe.get_subscribe(
            task_name="steam商店降价订阅", 
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
            WS_BOT_ID=ev.WS_BOT_ID,
            )
        
        if not price_info:
            await bot.send(f"您当前没有订阅的降价提醒")
            return
        
        send_msg = "[SteamUID] 当前降价提醒订阅列表\n"
        send_msg += "\n".join([sub.uid for sub in price_info if sub.uid])
        await bot.send(send_msg)

    except Exception as e:
        logger.exception(f"[SteamPrice] 查询命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")


@price_SV.on_command("测试降价订阅")
async def test_price_drop(bot: Bot, ev: Event):
    try:
        appid = await resolve_target_appid(bot, ev.text.strip())

        # 获取游戏基本信息与价格数据
        game_name = appid
        game_desc = ""
        cover_url = SteamAPI.GetGameCoverImageURL(appid, "header")
        discount_percent = 0
        original_price = ""
        final_price = ""

        try:
            game_data = await get_game_info(appid)
            if game_data and game_data.get("success"):
                d = game_data.get("data", {})
                game_name = d.get("name", appid)
                game_desc = d.get("short_description", "")
                cover_url = d.get("header_image") or cover_url

                price_overview = d.get("price_overview", {})
                if price_overview:
                    discount_percent = price_overview.get("discount_percent", 0)
                    original_price = price_overview.get("initial_formatted", "")
                    final_price = price_overview.get("final_formatted", "")
                elif d.get("is_free"):
                    final_price = "免费开玩"
        except Exception as e:
            logger.warning(f"[SteamPrice] 测试降价订阅获取游戏信息异常 appid={appid}: {e}")

        if not final_price:
            try:
                prices = await get_price_data(appid)
                po = prices.get(appid, {}).get("data", {}).get("price_overview", {})
                if po:
                    discount_percent = po.get("discount_percent", 0)
                    original_price = po.get("initial_formatted", "")
                    final_price = po.get("final_formatted", "")
            except Exception as e:
                logger.warning(f"[SteamPrice] 测试降价订阅补充获取价格异常 appid={appid}: {e}")

        # 渲染降价卡片
        img_bytes = await render_game_price_drop(
            game_name=game_name,
            game_desc=game_desc,
            cover_url=cover_url,
            discount_percent=discount_percent,
            original_price=original_price,
            final_price=final_price or "暂无价格信息",
        )

        send_msg = [
            MessageSegment.at(ev.user_id),
            MessageSegment.text("\n[Steam 降价订阅] 您订阅的游戏降价了！\n"),
            MessageSegment.image(img_bytes),
            MessageSegment.text(f"商店链接：https://store.steampowered.com/app/{appid}"),
        ]
        await bot.send(send_msg)

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamPrice] 测试降价订阅命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")