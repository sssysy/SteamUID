"""会话用户资料读取：昵称与头像统一取自框架 CoreUser。"""

from dataclasses import dataclass
from collections.abc import Sequence

from gsuid_core.models import Event
from gsuid_core.utils.database.models import CoreUser

_INVALID_VALUE = "1"


@dataclass(frozen=True)
class UserIdentity:
    """卡片头部所需的会话用户资料；头像缺失为空串。"""

    user_id: str
    name: str
    avatar_url: str


def _core_user_rows(raw: object) -> list[CoreUser]:
    """框架查询无类型标注，这里收窄为当前会话的用户行。"""
    if not isinstance(raw, Sequence):
        return []
    return [row for row in raw if isinstance(row, CoreUser)]


async def load_user_identity(ev: Event, user_id: str) -> UserIdentity:
    """按当前会话读取目标用户资料；未入库时昵称回落目标 ID。"""
    bot_id = ev.real_bot_id if ev.real_bot_id else ev.bot_id
    rows = _core_user_rows(
        await CoreUser.select_rows(
            bot_id=bot_id,
            user_id=user_id,
            group_id=ev.group_id,
        )
    )
    if not rows:
        return UserIdentity(user_id=user_id, name=user_id, avatar_url="")

    row = rows[0]
    name = row.user_name if row.user_name and row.user_name != _INVALID_VALUE else user_id
    avatar = row.user_icon if row.user_icon and row.user_icon != _INVALID_VALUE else ""
    if not avatar.startswith(("http://", "https://")):
        avatar = ""
    return UserIdentity(user_id=user_id, name=name, avatar_url=avatar)
