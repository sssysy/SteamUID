"""等级徽章素材：官方图案按需下载落 img_cache，缺失时回落纯色圆环。"""

from dataclasses import dataclass

from gsuid_core.logger import logger

from ..downloader import download
from ..maps import level_style
from ..api.endpoints import COMMUNITY_CDN_BASE_DEFAULT, COMMUNITY_LEVEL_SPRITE

_TAG = "[Steam·信息卡片]"


@dataclass(frozen=True)
class LevelBadge:
    """等级徽章：圆环色恒有，图案为 img_cache 文件名（无图案时为空串）。"""

    level: int
    border_color: str
    sprite_name: str
    offset_px: int


async def load_level_badge(level: int) -> LevelBadge:
    """按等级取官方图案；下载失败只告警并回落圆环，不影响出图。"""
    style = level_style(level)
    sprite_name = ""
    if style.sprite_file:
        url = (
            COMMUNITY_CDN_BASE_DEFAULT
            + COMMUNITY_LEVEL_SPRITE.format(name=style.sprite_file)
        )
        path = await download(url, kind="image")
        if path is None:
            logger.warning(f"{_TAG} 等级图案下载失败: {style.sprite_file}")
        else:
            sprite_name = path.name

    return LevelBadge(
        level=level,
        border_color=style.border_color,
        sprite_name=sprite_name,
        offset_px=style.offset_px,
    )
