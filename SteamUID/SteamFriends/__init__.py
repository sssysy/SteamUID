from asyncio import timeout

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV, get_plugin_available_prefix

from ..utils.database.models import SteamBind
from ..SteamConfig import SteamConfig
from ..utils.utils import steamid64_to_friend_code, maybe_hide_steamid
from ..utils.exceptions import SteamValidationError

friends_SV = SV("steam好友相关")

@friends_SV.on_command("加好友")
async def add_friend(bot: Bot, ev: Event):
    try:
        if not SteamConfig.get_config("AllowAddFriends").data:
            raise SteamValidationError("管理员未开放此功能")
        if not ev.at:
            raise SteamValidationError("请 @ 要添加好友的人")
        if ev.user_id == ev.at:
            raise SteamValidationError("不能 @ 自己添加好友")

        steamid64 = await SteamBind.get_main_id(ev.bot_id, ev.at, ev.user_type, ev.group_id)
        if not steamid64:
            raise SteamValidationError("此用户未在此处绑定 Steam 账号")
        
        prefix = get_plugin_available_prefix("SteamUID")
        await bot.send([MessageSegment.at(ev.at), MessageSegment.text(f"有人正在请求获取您的 steam 好友码\n发送 {prefix}同意/拒绝 来同意/拒绝好友请求")])
        try:
            async with timeout(60):
                while True:
                    resp = await bot.receive_mutiply_resp()
                    if not resp:
                        continue

                    if resp.text.strip() in ("同意", "允许", "通过", "批准", "放行") and resp.user_id == ev.at and resp.group_id == ev.group_id:

                        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text(f"对方已同意你的好友请求。\n请添加以下好友码：{maybe_hide_steamid(steamid64_to_friend_code(steamid64))}")])
                        break

                    elif resp.text.strip() in ("拒绝", "不允许", "不批准", "不放行", "不通过") and resp.user_id == ev.at and resp.group_id == ev.group_id:
                        await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text("对方已拒绝你的好友请求。")])
                        break
        except TimeoutError:
            await bot.send([MessageSegment.at(ev.user_id), MessageSegment.text("对方未回复，操作取消。")])
    
    except SteamValidationError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamFriends] 加好友命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")