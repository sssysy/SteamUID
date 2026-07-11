from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..utils.PIL.draw import draw_bind_list_photo
from ..utils.exceptions import SteamError, SteamValidationError
from ..utils.utils import auto2steamid64, steamid64_to_friend_code
from . import login
from .bind_service import (
    do_bind,
    do_unbind,
    get_bind_card_data,
    switch_main_id,
)

bind_sv = SV("绑定账号")


async def _send_bind_card(
    bot: Bot,
    ev: Event,
    *,
    fallback_msg: str | None = None,
    new_bind_steamid: str | None = None,
    unbind_banner: dict | None = None,
    show_all: bool = True,
) -> None:
    """获取绑定数据并渲染发送卡片图片，渲染失败时回退到文字"""
    try:
        now_items, other_items = await get_bind_card_data(
            ev.bot_id, ev.user_id, ev.user_type, ev.group_id, show_all
        )
        img = await draw_bind_list_photo(
            now_items, other_items,
            new_bind_steamid=new_bind_steamid,
            unbind_banner=unbind_banner,
        )
        await bot.send(MessageSegment.image(img))
    except Exception as e:
        logger.warning(f"[SteamBind] 渲染绑定卡片失败，回退到文字: {e}")
        if fallback_msg:
            await bot.send(fallback_msg)


@bind_sv.on_command(("绑定", "登录", "登陆", "bind"))
async def steambind(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if steamid64:
            if SteamConfig.get_config("OnlyOpenID").data:
                raise SteamValidationError("仅允许网页登录，不支持手动绑定steamid！")
        else:
            steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            success_msg, warning = await do_bind(ev, steamid64)
            fallback = success_msg
            if warning:
                fallback += f"\n{warning}"
            await _send_bind_card(
                bot, ev, fallback_msg=fallback, new_bind_steamid=steamid64
            )
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 绑定命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command(("解绑", "unbind", "退出登录", "退出登陆"))
async def steamunbind(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if not steamid64:
            await bot.send("请在接下来登录一次要解绑的 steam 以继续")
            steamid64 = await login.request_openid_login(bot, ev)
        if steamid64:
            # 解绑前获取玩家信息用于横幅
            from ..utils.database.models import SteamIDInfo
            import json as _json

            info_json = await SteamIDInfo.get_steamuserinfo(steamid64)
            if info_json:
                info = _json.loads(info_json)
            else:
                from ..utils.api import get_user_Summaries

                sid_info = await get_user_Summaries(steamid64)
                info = sid_info[0] if sid_info else {}

            banner = {
                "name": info.get("personaname", "未知用户"),
                "friend_code": steamid64_to_friend_code(steamid64),
            }

            msg = await do_unbind(ev, steamid64)
            await _send_bind_card(bot, ev, fallback_msg=msg, unbind_banner=banner)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 解绑命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command("查看")
async def steamview(bot: Bot, ev: Event):
    try:
        at = ev.at
        if at:
            if not SteamConfig.get_config("AllowAt").data:
                raise SteamValidationError("管理员未开放 @ 他人查询功能")
            ev.user_id = at
        show_all = ev.text.strip() == "全部"
        now_items, other_items = await get_bind_card_data(
            ev.bot_id, ev.user_id, ev.user_type, ev.group_id, show_all
        )
        if not now_items and not other_items:
            await bot.send("未绑定任何 steamid")
        else:
            img = await draw_bind_list_photo(now_items, other_items)
            await bot.send(MessageSegment.image(img))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 查看命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")


@bind_sv.on_command("切换")
async def switchsteamid(bot: Bot, ev: Event):
    try:
        text = ev.text.strip()
        steamid64 = auto2steamid64(text)
        if not steamid64:
            raise SteamValidationError("请输入正确的steamid或好友码")
        msg = await switch_main_id(ev, steamid64)
        await bot.send(msg)
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamBind] 切换命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")
