"""排行通用逻辑：游玩时长的展示格式化与群成员 QQ 资料抓取。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Sequence

import httpx
from gsuid_core.logger import logger
from gsuid_core.utils.database.models import CoreUser

from ..downloader import download

_TAG = "[Steam·排行]"
_MINUTE_SECONDS = 60
_HOUR_SECONDS = 3600


def format_duration(seconds: int) -> str:
    """游玩时长：不足 1 小时按分钟一位小数，否则按小时一位小数。"""
    if seconds < _HOUR_SECONDS:
        return f"{seconds / _MINUTE_SECONDS:.1f}min"
    return f"{seconds / _HOUR_SECONDS:.1f}h"


@dataclass(frozen=True)
class GroupMember:
    """群成员的展示资料；头像为 img_cache 文件名，缺失为空串。"""

    name: str
    avatar_name: str


async def _icon_name(icon: str) -> str:
    """群头像落 img_cache 后返回文件名；空 URL 或失败返回空串。"""
    try:
        path = await download(icon, kind="image")
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 群头像下载失败: {type(error).__name__}")
        return ""
    return path.name if path is not None else ""


async def _member(user_id: str, group_id: str) -> GroupMember:
    """取群名片与头像；名片缺失回落用户 ID，头像缺失留空串。"""
    row = await CoreUser.base_select_data(user_id=user_id, group_id=group_id)
    name = user_id
    avatar_name = ""
    if row is not None:
        if row.user_name and row.user_name != "1":
            name = str(row.user_name)
        if row.user_icon and row.user_icon != "1":
            avatar_name = await _icon_name(row.user_icon)
    return GroupMember(name=name, avatar_name=avatar_name)


async def load_group_members(
    group_id: str, user_ids: Sequence[str]
) -> dict[str, GroupMember]:
    """并发取一批群成员资料，返回 user_id 到资料的映射。"""
    ordered = list(dict.fromkeys(user_ids))
    if not ordered:
        return {}
    members = await asyncio.gather(*(_member(uid, group_id) for uid in ordered))
    return dict(zip(ordered, members))
