import asyncio
from types import SimpleNamespace

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV
from gsuid_core.segment import MessageSegment
from gsuid_core.logger import logger

from ..utils.target import resolve_target_steamid64
from ..utils.api import (
    get_user_Summaries,
    get_profile_items_equipped,
    get_miniprofile,
)
from ..utils.steam_status import resolve_player_status
from ..utils.render import render_miniprofile, render_html, render_html_gif
from ..utils.exceptions import SteamValidationError, SteamAPIError, SteamError

user_sv = SV("steam用户相关")

# personastate → (persona_class, status_class, status_text)
_STATUS_MAP = {
    1: ("online", "online", "在线"),
    2: ("online", "online", "忙碌"),
    3: ("online", "online", "离开"),
    4: ("online", "online", "打盹"),
    5: ("online", "online", "想交易"),
    6: ("online", "online", "想游玩"),
}


@user_sv.on_command("状态")
async def steamstatus(bot: Bot, ev: Event):
    try:
        steamid64 = await resolve_target_steamid64(ev, ev.text.strip())
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        # 1. 获取玩家摘要（含可见性检查）
        players = await get_user_Summaries(steamid64)
        if not players:
            raise SteamAPIError("未找到该 Steam 用户")
        player = players[0]

        # 2. 私有资料检查
        if player.get("communityvisibilitystate", 3) == 1:
            raise SteamValidationError("该用户资料为私有，无法查看详细信息")

        # 3. 并发获取 miniprofile JSON + 装备项
        miniprofile_data, items_data = await asyncio.gather(
            get_miniprofile(steamid64),
            get_profile_items_equipped(steamid64),
            return_exceptions=True,
        )

        # 4. 解析状态
        status, game_name = resolve_player_status(player)
        if status == "in-game":
            persona_cls, status_cls = "in-game", "in-game"
            status_text = f"游戏中：{game_name}" if game_name else "游戏中"
        elif status == "offline":
            persona_cls, status_cls, status_text = "offline", "offline", "离线"
        else:
            state = player.get("personastate", 0)
            persona_cls, status_cls, status_text = _STATUS_MAP.get(
                state, ("online", "online", "在线")
            )
        border_cls = f"border_color_{status_cls}"

        # 5. 解析等级
        level_num = "0"
        level_classes = "lvl_0"
        if isinstance(miniprofile_data, dict):
            level = miniprofile_data.get("level", 0)
            level_num = str(level)
            level_class = miniprofile_data.get("level_class", "")
            if level_class:
                level_classes = level_class.replace("friendPlayerLevel", "").strip()

        # 6. 解析头像（动画头像 > miniprofile头像 > 摘要头像）
        avatar_url = player.get("avatarfull", "")
        if isinstance(miniprofile_data, dict) and miniprofile_data.get("avatar_url"):
            avatar_url = miniprofile_data["avatar_url"]
        if isinstance(items_data, dict):
            animated = items_data.get("animated_avatar", {})
            if animated.get("image_small"):
                avatar_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{animated['image_small']}"

        # 7. 解析头像框（优先 miniprofile JSON 完整 URL，回退 GetProfileItemsEquipped）
        avatar_frame_url = None
        if isinstance(miniprofile_data, dict):
            avatar_frame_url = miniprofile_data.get("avatar_frame")
        if not avatar_frame_url and isinstance(items_data, dict):
            frame = items_data.get("avatar_frame", {})
            if frame.get("image_small"):
                avatar_frame_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{frame['image_small']}"

        # 8. 解析背景（miniprofile视频 > 装备项静态图片 > 默认渐变）
        bg_webm = bg_mp4 = bg_img = None
        if isinstance(miniprofile_data, dict):
            bg = miniprofile_data.get("profile_background", {})
            bg_webm = bg.get("video/webm")
            bg_mp4 = bg.get("video/mp4")
        if isinstance(items_data, dict) and not bg_webm and not bg_mp4:
            mini_bg = items_data.get("mini_profile_background", {})
            if mini_bg.get("image_large"):
                bg_img = f"https://shared.fastly.steamstatic.com/community_assets/images/{mini_bg['image_large']}"

        # 9. 解析特色徽章
        badge_icon_url = badge_name = badge_xp = None
        if isinstance(miniprofile_data, dict):
            badge = miniprofile_data.get("favorite_badge")
            if badge:
                badge_icon_url = badge.get("icon")
                badge_name = badge.get("name")
                badge_xp = str(badge.get("xp", "")) if badge.get("xp") else None

        # 10. 构建数据对象并渲染
        data = SimpleNamespace(
            avatar_url=avatar_url,
            avatar_frame_url=avatar_frame_url,
            background_video_webm=bg_webm,
            background_video_mp4=bg_mp4,
            background_image_url=bg_img,
            persona_name=player.get("personaname", ""),
            persona_class=persona_cls,
            status_class=status_cls,
            status_text=status_text,
            border_color_class=border_cls,
            level_num=level_num,
            level_classes=level_classes,
            badge_icon_url=badge_icon_url,
            badge_name=badge_name,
            badge_xp=badge_xp,
        )

        html = render_miniprofile(data)

        # 检测动态内容：视频背景 / GIF 动态头像 / GIF 动态头像框
        has_dynamic = (
            bool(bg_webm or bg_mp4)
            or (bool(avatar_url) and avatar_url.endswith(".gif"))
            or (bool(avatar_frame_url) and avatar_frame_url.endswith(".gif"))
        )

        if has_dynamic:
            img_bytes = await render_html_gif(html, ".miniprofile_container")
        else:
            img_bytes = await render_html(html, ".miniprofile_container")
        await bot.send(MessageSegment.image(img_bytes))
    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.error(f"[SteamUser] 状态命令异常: {e}")
        await bot.send(f"发生未知错误: {e}")