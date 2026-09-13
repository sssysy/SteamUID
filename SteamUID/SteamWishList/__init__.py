import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig, get_current_currency
from ..utils.Api import (
    get_game_cover_url,
    get_game_info,
    get_miniprofile,
    get_price_data,
    get_profile_items_equipped,
    get_user_Summaries,
    get_user_wishlist,
)
from ..utils.database.models import SteamBind
from ..utils.exceptions import (
    SteamAPIError,
    SteamConfigError,
    SteamError,
    SteamValidationError,
    unwrap,
)
from ..utils.helpers.price import format_price
from ..utils.helpers.profile import resolve_profile_assets
from ..utils.helpers.steam_state import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from ..utils.render import render_wishlist
from ..utils.helpers.command import steam_command
from ..utils.utils import (
    auto2steamid64,
    resolve_target_steamid64,
    steamid64_to_friend_code,
)

wishlist_sv = SV("steam愿望单相关")


@steam_command("SteamWishList", fallback="查询愿望单列表发生未知错误，详情请查看后台。")
@wishlist_sv.on_command(("愿望单列表", "愿望单", "愿望清单", "wishlist"), block=True)
async def get_wishlist_card(bot: Bot, ev: Event):
    """获取指定 Steam 用户的愿望单列表并渲染为图片。"""
    # 1. 检查 Steam Web API Key 配置
    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    # 2. 解析目标 SteamID64
    target_user_id = ev.user_id
    target_steamid64 = None

    if ev.at:
        if not SteamConfig.get_config("AllowAt").data:
            raise SteamValidationError("未开启 @ 他人获取他人信息功能")
        target_user_id = ev.at
    else:
        # 单参数命令：第一个 token 即好友码/steamid64
        words = ev.text.strip().split()
        if words:
            target_steamid64 = auto2steamid64(words[0])

    if target_steamid64:
        steamid64 = target_steamid64
    else:
        is_self = target_user_id == ev.user_id
        if is_self:
            steamid64 = await SteamBind.get_main_id(
                ev.bot_id, ev.user_id, ev.user_type, ev.group_id
            )
        else:
            binds = await SteamBind.get_binds_by_user(
                ev.bot_id, target_user_id, ev.user_type, ev.group_id
            )
            if not binds:
                raise SteamValidationError("对方在当前群未绑定 Steam 账号")
            steamid64 = next((b.steamid64 for b in binds if b.is_main_id), None)
            if not steamid64:
                raise SteamValidationError(
                    "对方未设置主 Steam 账号，请先使用【steam切换】设置主账号"
                )

    if not steamid64:
        raise SteamValidationError("未找到目标绑定的 Steam 账号，请先绑定！")

    # 3. 并发获取用户信息与愿望单数据
    players_res, miniprofile_data, items_data, wishlist_items = await asyncio.gather(
        get_user_Summaries(steamid64),
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        get_user_wishlist(steamid64),
        return_exceptions=True,
    )

    if isinstance(players_res, SteamError):
        raise players_res
    if isinstance(wishlist_items, SteamError):
        raise wishlist_items

    # 4. 基础资料校验与私有检查
    if isinstance(players_res, Exception) or not players_res:
        raise SteamAPIError("未找到该 Steam 用户")
    player = players_res[0]

    if isinstance(wishlist_items, Exception) or not wishlist_items:
        if player.get("communityvisibilitystate", VISIBILITY_PUBLIC) == VISIBILITY_PRIVATE:
            raise SteamValidationError("该用户资料为私有，无法查看愿望单")
        raise SteamValidationError("该账号愿望单为空或已设置为私有")

    # 5. 构建用户账号药丸信息 (user_data)
    assets = await resolve_profile_assets(
        steamid64,
        player=player,
        miniprofile_data=miniprofile_data,
        items_data=items_data,
    )
    user_data = {
        "name": player.get("personaname", "未知用户"),
        "friend_code": steamid64_to_friend_code(steamid64),
        "avatar_url": assets.avatar_url,
        "avatar_frame_url": assets.avatar_frame_url,
        "bg_url": assets.bg_url,
    }

    # 6. 处理愿望单条数（默认全部，超过20条截断并在末尾显示 ...）
    total_count = len(wishlist_items)
    max_display = 20
    if total_count > max_display:
        top_items = wishlist_items[:max_display]
        has_more = True
        remaining_count = total_count - max_display
    else:
        top_items = wishlist_items
        has_more = False
        remaining_count = 0

    appids = [str(it["appid"]) for it in top_items]

    # 限制并发拉取详情
    sem = asyncio.Semaphore(15)

    async def fetch_game_info_safe(aid: str):
        async with sem:
            try:
                return await get_game_info(aid)
            except Exception:
                return None

    prices_res, game_info_results = await asyncio.gather(
        get_price_data(appids),
        asyncio.gather(*[fetch_game_info_safe(aid) for aid in appids], return_exceptions=True),
        return_exceptions=True,
    )

    prices_map = unwrap(prices_res, {}, expect=dict)
    game_info_list = unwrap(game_info_results, [], expect=list)

    # 7. 组装愿望单每项数据
    wishlist_data = []
    for idx, (it, aid) in enumerate(zip(top_items, appids)):
        game_name = aid
        game_info = game_info_list[idx] if idx < len(game_info_list) else None
        g_data = {}
        header_img = None
        if isinstance(game_info, dict) and game_info.get("success"):
            g_data = game_info.get("data", {})
            if isinstance(g_data, dict):
                if g_data.get("name"):
                    game_name = g_data["name"]
                header_img = g_data.get("header_image")

        cover_url = await get_game_cover_url(aid, header_image=header_img)

        # 价格与状态安全解析
        is_free = False
        is_unreleased = False
        discount_pct = 0
        price_str = ""
        price_overview = None

        # 1. 优先从 get_price_data 获取 price_overview
        p_entry = prices_map.get(aid)
        if isinstance(p_entry, dict):
            p_data = p_entry.get("data")
            if isinstance(p_data, dict):
                price_overview = p_data.get("price_overview")

        # 2. 回退从 get_game_info 获取 price_overview
        if not isinstance(price_overview, dict) and isinstance(g_data, dict):
            po = g_data.get("price_overview")
            if isinstance(po, dict):
                price_overview = po

        # 3. 状态与价格字符串判定
        if isinstance(g_data, dict) and g_data.get("is_free"):
            is_free = True
            price_str = "免费"
        elif isinstance(price_overview, dict):
            final_fmt = price_overview.get("final_formatted")
            discount_pct = int(price_overview.get("discount_percent") or 0)
            price_str = (
                str(final_fmt)
                if final_fmt
                else format_price(price_overview.get("final", 0), get_current_currency())
            )
        else:
            release_info = g_data.get("release_date") if isinstance(g_data, dict) else None
            if isinstance(release_info, dict) and release_info.get("coming_soon"):
                is_unreleased = True
                price_str = "即将推出"
            else:
                is_unreleased = True
                price_str = "暂无定价"

        wishlist_data.append({
            "appid": aid,
            "game_name": game_name,
            "cover_url": cover_url,
            "date_added": it.get("date_added"),
            "price_str": price_str,
            "discount_percent": discount_pct,
            "is_free": is_free,
            "is_unreleased": is_unreleased,
        })

    # 8. 渲染并发送卡片
    title_text = "steam 愿望单列表"

    img_bytes = await render_wishlist(
        wishlist_data=wishlist_data,
        user_data=user_data,
        title_text=title_text,
        canvas_width=800,
        has_more=has_more,
        remaining_count=remaining_count,
    )
    await bot.send(MessageSegment.image(img_bytes))

