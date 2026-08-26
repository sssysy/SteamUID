import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..SteamConfig import SteamConfig
from ..utils.api import (
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
)
from ..utils.render import render_wishlist
from ..utils.utils import (
    auto2steamid64,
    resolve_target_steamid64,
    steamid64_to_friend_code,
)

wishlist_sv = SV("steam愿望单相关")


@wishlist_sv.on_command(("愿望单列表", "愿望单", "愿望清单", "wishlist"))
async def get_wishlist_card(bot: Bot, ev: Event):
    """获取指定 Steam 用户的愿望单列表并渲染为图片。"""
    try:
        # 1. 检查 Steam Web API Key 配置
        api_key = SteamConfig.get_config("SteamWebAPIKey").data
        if not api_key:
            raise SteamConfigError("请先配置 steam web api key")

        # 2. 解析目标 SteamID64 与条数限制
        limit = 10
        target_user_id = ev.user_id
        target_steamid64 = None

        if ev.at:
            if not SteamConfig.get_config("AllowAt").data:
                raise SteamValidationError("未开启 @ 他人获取他人信息功能")
            target_user_id = ev.at
            text = ev.text.strip()
            if text.isdigit() and int(text) > 0:
                limit = int(text)
        else:
            words = ev.text.strip().split()
            for word in words:
                if not word.isdigit():
                    continue
                sid = auto2steamid64(word)
                if sid and (int(word) > 1000 or len(word) >= 5):
                    target_steamid64 = sid
                elif int(word) > 0:
                    limit = int(word)

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
                steamid64 = next((b.steamid64 for b in binds if b.is_main_id), binds[0].steamid64)

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

        # 4. 基础资料校验与私有检查
        if isinstance(players_res, Exception) or not players_res:
            raise SteamAPIError("未找到该 Steam 用户")
        player = players_res[0]

        if player.get("communityvisibilitystate", 3) == 1:
            raise SteamValidationError("该用户资料为私有，无法查看愿望单")

        if isinstance(wishlist_items, Exception) or not wishlist_items:
            raise SteamValidationError("该账号愿望单为空或已设置为私有")

        # 5. 构建用户账号药丸信息 (user_data)
        user_name = player.get("personaname", "未知用户")
        friend_code = steamid64_to_friend_code(steamid64)

        avatar_url = player.get("avatarfull", "")
        if isinstance(miniprofile_data, dict) and miniprofile_data.get("avatar_url"):
            avatar_url = miniprofile_data["avatar_url"]

        avatar_frame_url = None
        if isinstance(items_data, dict):
            frame = items_data.get("avatar_frame", {})
            if frame.get("image_small"):
                avatar_frame_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"
        if not avatar_frame_url and isinstance(miniprofile_data, dict):
            avatar_frame_url = miniprofile_data.get("avatar_frame")

        bg_url = None
        if isinstance(items_data, dict):
            mini_bg = items_data.get("mini_profile_background", {})
            if mini_bg.get("image_large"):
                bg_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{mini_bg['image_large']}"
        if not bg_url and isinstance(miniprofile_data, dict):
            bg = miniprofile_data.get("profile_background", {})
            bg_url = bg.get("image")

        user_data = {
            "name": user_name,
            "friend_code": friend_code,
            "avatar_url": avatar_url,
            "avatar_frame_url": avatar_frame_url,
            "bg_url": bg_url,
        }

        # 6. 处理愿望单条数与批量获取价格与详情
        top_items = wishlist_items[:limit]
        appids = [str(it["appid"]) for it in top_items]

        prices_res, game_info_results = await asyncio.gather(
            get_price_data(appids),
            asyncio.gather(*[get_game_info(aid) for aid in appids], return_exceptions=True),
            return_exceptions=True,
        )

        prices_map = prices_res if isinstance(prices_res, dict) else {}
        game_info_list = game_info_results if isinstance(game_info_results, list) else []

        # 7. 组装愿望单每项数据
        wishlist_data = []
        for idx, (it, aid) in enumerate(zip(top_items, appids)):
            game_name = aid
            cover_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"

            game_info = game_info_list[idx] if idx < len(game_info_list) else None
            g_data = {}
            if isinstance(game_info, dict) and game_info.get("success"):
                g_data = game_info.get("data", {})
                if g_data.get("name"):
                    game_name = g_data["name"]
                if g_data.get("header_image"):
                    cover_url = g_data["header_image"]

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
                price_str = str(final_fmt) if final_fmt else f"¥ {price_overview.get('final', 0) / 100:.2f}"
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
        total_count = len(wishlist_items)
        disp_count = len(wishlist_data)
        title_text = f"steam 愿望单列表 Top{disp_count}: " if total_count > disp_count else f"steam 愿望单列表 (共{disp_count}款): "

        img_bytes = await render_wishlist(
            wishlist_data=wishlist_data,
            user_data=user_data,
            title_text=title_text,
            canvas_width=800,
        )
        await bot.send(MessageSegment.image(img_bytes))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamWishList] 愿望单列表命令异常: {e!r}")
        await bot.send("查询愿望单列表发生未知错误，详情请查看后台。")
