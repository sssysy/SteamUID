from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV
from gsuid_core.subscribe import gs_subscribe

from ..utils.database.models import SteamPriceInfo
from ..utils.api import get_price_data
from ..SteamConfig import SteamConfig
import json



price_SV = SV("steam商店降价提醒")

@price_SV.on_command("订阅降价")
async def steamsubscribe(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        if not text:
            await bot.send("请携带要订阅降价提醒的 appid")
            return
        appid = text
        
        cc = SteamConfig.get_config("pricecc").data
        first_prices = await get_price_data(appid)
        if not first_prices.get(appid, {}).get("success", False):
            await bot.send(f"订阅失败！\n原因: 获取该游戏价格失败！请确认该 appid 在 {cc} 区是否锁区！")
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
    except Exception as e:
        logger.warning(f"[SteamPrice] 订阅命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")

@price_SV.on_command("取消订阅降价")
async def steam_unsubscribe(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        if not text:
            await bot.send("请携带要取消订阅降价提醒的 appid")
            return
        appid = text

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

    except Exception as e:
        logger.warning(f"[SteamPrice] 取消订阅命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")

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
        logger.warning(f"[SteamPrice] 查询命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")