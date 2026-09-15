import asyncio
from types import SimpleNamespace

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV
from gsuid_core.segment import MessageSegment
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig
from ..utils.Api import (
    get_user_Summaries,
    get_profile_items_equipped,
    get_miniprofile,
    get_steamlibrary_by_steamid64,
    is_private_data_allowed,
)
from .user_service import (
    get_player_bio,
    calculate_account_value,
    refresh_user_cache,
)
from ..utils.database.models import SteamBind, SteamNextAccount
from ..utils.helpers.profile import calc_account_age, resolve_profile_assets
from ..utils.helpers.steam_state import (
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    get_persona_status,
    resolve_player_status,
)
from ..utils.utils import (
    country_code_to_flag,
    steamid64_to_friend_code,
    maybe_hide_steamid,
    resolve_target_steamid64,
)
from ..utils.render import render_miniprofile, render_html, render_html_gif, render_steam_info
from ..utils.exceptions import SteamValidationError, SteamAPIError, SteamConfigError
from ..SteamBind import _send_bind_card
from ..utils.helpers.command import steam_command


user_sv = SV("steam用户相关")


@steam_command("SteamUser")
@user_sv.on_command("状态")
async def steamstatus(bot: Bot, ev: Event):
    steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
    if not steamid64:
        raise SteamValidationError("请先绑定 steam 账号")

    # 1. 获取玩家摘要（含可见性检查）
    players = await get_user_Summaries(steamid64)
    if not players:
        raise SteamAPIError("未找到该 Steam 用户")
    player = players[0]

    # 2. 私有资料检查
    if player.get("communityvisibilitystate", VISIBILITY_PUBLIC) == VISIBILITY_PRIVATE:
        has_auth = is_private_data_allowed() and bool(
            await SteamNextAccount.get_account(steamid64)
        )
        if not has_auth:
            raise SteamValidationError("该用户资料为私有，无法查看详细信息")

    # 3. 解析状态
    status, game_name = resolve_player_status(player)
    if status == "ingame":
        persona_cls, status_cls = "in-game", "in-game"
        status_text = f"游戏中：{game_name}" if game_name else "游戏中"
    elif status == "offline":
        persona_cls, status_cls, status_text = "offline", "offline", "离线"
    else:
        state = player.get("personastate", 0)
        persona_cls, status_cls, status_text = get_persona_status(state)
    border_cls = f"border_color_{status_cls}"

    # 4. 统一解析装扮资产（等级 / 头像 / 头像框 / 背景 / 徽章）
    assets = await resolve_profile_assets(
        steamid64, player=player, include_animated=True
    )

    # 5. 构建数据对象并渲染（有视频背景时不再叠加静态图）
    data = SimpleNamespace(
        avatar_url=assets.avatar_url,
        avatar_frame_url=assets.avatar_frame_url,
        background_video_webm=assets.bg_video_webm,
        background_video_mp4=assets.bg_video_mp4,
        background_image_url=None if assets.has_bg_video else assets.bg_url,
        persona_name=player.get("personaname", ""),
        persona_class=persona_cls,
        status_class=status_cls,
        status_text=status_text,
        border_color_class=border_cls,
        level_num=assets.level_num,
        level_classes=assets.level_classes,
        badge_icon_url=assets.badge_icon_url,
        badge_name=assets.badge_name,
        badge_xp=assets.badge_xp,
    )

    html = render_miniprofile(data)

    # 检测动态内容：视频背景 / 动画头像（以接口字段为准，不猜 URL 后缀）
    has_dynamic = assets.has_bg_video or assets.has_animated_avatar

    if has_dynamic:
        img_bytes = await render_html_gif(html, ".miniprofile_container")
    else:
        img_bytes = await render_html(html, ".miniprofile_container")
    await bot.send(MessageSegment.image(img_bytes))


@steam_command("SteamUser")
@user_sv.on_command(("信息", "steam信息", "info", "steaminfo"))
async def steam_info(bot: Bot, ev: Event):
    steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
    if not steamid64:
        raise SteamValidationError("请先绑定 steam 账号")

    api_key = SteamConfig.get_config("SteamWebAPIKey").data
    if not api_key:
        raise SteamConfigError("请先配置 steam web api key")

    # 1. 获取玩家摘要（含可见性检查）
    players = await get_user_Summaries(steamid64)
    if not players:
        raise SteamAPIError("未找到该 Steam 用户")
    player = players[0]

    # 2. 私有资料检查
    if player.get("communityvisibilitystate", VISIBILITY_PUBLIC) == VISIBILITY_PRIVATE:
        has_auth = is_private_data_allowed() and bool(
            await SteamNextAccount.get_account(steamid64)
        )
        if not has_auth:
            raise SteamValidationError("该用户资料为私有，无法查看详细信息")

    # 3. 并发获取 miniprofile JSON + 装备项 + 游戏库 + 个人简介
    miniprofile_data, items_data, library_data, bio_text = await asyncio.gather(
        get_miniprofile(steamid64),
        get_profile_items_equipped(steamid64),
        get_steamlibrary_by_steamid64(api_key, steamid64),
        get_player_bio(steamid64),
        return_exceptions=True,
    )

    # 4. 解析状态与状态颜色
    status, game_name = resolve_player_status(player)
    if status == "ingame":
        status_cls = "ingame"
        status_text = f"游戏中：{game_name}" if game_name else "游戏中"
    elif status == "offline":
        status_cls = "offline"
        status_text = "离线"
    else:
        state = player.get("personastate", 0)
        _, _, status_text = get_persona_status(state)
        status_cls = "online"

    # 5. 统一解析装扮资产（等级 / 头像 / 头像框 / 静态背景 / 徽章）
    assets = await resolve_profile_assets(
        steamid64,
        player=player,
        miniprofile_data=miniprofile_data,
        items_data=items_data,
    )

    # 10. 解析地区与注册年限
    region = country_code_to_flag(player.get("loccountrycode"))
    account_age = calc_account_age(player.get("timecreated"))

    # 11. 解析游戏库统计（总数量、总时长、账号价值）
    games = []
    if isinstance(library_data, dict) and library_data.get("games"):
        games = library_data["games"]

    game_count = str(len(games))
    total_playtime_minutes = sum(
        (g.get("playtime_forever", 0) or
         g.get("playtime_windows_forever", 0) +
         g.get("playtime_mac_forever", 0) +
         g.get("playtime_linux_forever", 0) +
         g.get("playtime_deck_forever", 0))
        for g in games
    )
    playtime_hours = str(int(round(total_playtime_minutes / 60)))
    account_value = str(await calculate_account_value(games))

    # 12. 解析 Steam ID
    friend_code = steamid64_to_friend_code(steamid64)
    steam_id_display = maybe_hide_steamid(friend_code)

    # 13. 个人简介
    clean_bio = bio_text if isinstance(bio_text, str) else ""

    # 14. 组装数据并静态渲染
    data = SimpleNamespace(
        avatar_url=assets.avatar_url,
        avatar_frame_url=assets.avatar_frame_url,
        background_image_url=assets.bg_url,
        persona_name=player.get("personaname", ""),
        status_class=status_cls,
        status_text=status_text,
        badge_icon_url=assets.badge_icon_url,
        bio_text=clean_bio,
        level_num=assets.level_num,
        level_classes=assets.level_classes,
        region=region,
        account_age=account_age,
        account_value=account_value,
        playtime_hours=playtime_hours,
        game_count=game_count,
        steam_id_display=steam_id_display,
    )

    img_bytes = await render_steam_info(data)
    await bot.send(MessageSegment.image(img_bytes))


@steam_command("SteamUser", fallback="刷新用户缓存失败，详情请查看后台。")
@user_sv.on_command(("刷新用户", "更新用户", "刷新资料"))
async def refresh_user(bot: Bot, ev: Event):
    # 1. 查找当前用户绑定的所有 Steam 账号
    binds = await SteamBind.get_binds_by_user(
        bot_id=ev.bot_id,
        user_id=ev.user_id,
        user_type=ev.user_type,
    )
    if not binds:
        raise SteamValidationError("你尚未绑定任何 Steam 账号！")

    steamids = list({b.steamid64 for b in binds if b.steamid64})
    if not steamids:
        raise SteamValidationError("未找到有效的绑定账号！")

    # 2. 重新获取所有账户信息缓存
    await refresh_user_cache(steamids)

    # 3. 渲染发送最新的绑定卡片图片
    await _send_bind_card(
        bot,
        ev,
        fallback_msg=f"[SteamUID] 成功刷新 {len(steamids)} 个 Steam 账号的个人信息与装扮缓存！",
        show_all=True,
    )