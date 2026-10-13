"""插件额外信息：向 core 状态图注册本插件的运行指标。"""

from pathlib import Path
from collections.abc import Sequence

from PIL import Image

from gsuid_core.subscribe import gs_subscribe
from gsuid_core.status.plugin_status import register_status
from gsuid_core.utils.database.models import Subscribe

from ..utils.helper.price_drop import SUBSCRIBE_TASK
from ..utils.database.model_auth import SteamAuth
from ..utils.database.model_bind import SteamBind

ICON = Path(__file__).resolve().parent.parent.parent / "ICON.png"


def _subscribe_rows(rows: object) -> list[Subscribe]:
    """框架订阅接口无类型标注，这里立刻收窄为 Subscribe。"""
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Subscribe)]


async def get_bind_num() -> int:
    """去重 steamid64 数，同一账号在多会话绑定只算一次。"""
    return len(await SteamBind.get_all_steamids())


async def get_auth_num() -> int:
    """已登录账号数，一个 steamid64 一行。"""
    return len(await SteamAuth.get_all_accounts())


async def get_price_sub_num() -> int:
    """被订阅降价的游戏数，按 appid 去重。"""
    rows = _subscribe_rows(await gs_subscribe.get_subscribe(SUBSCRIBE_TASK))
    return len({row.uid for row in rows if row.uid})


register_status(
    Image.open(ICON).convert("RGBA"),
    "SteamUID",
    {
        "绑定账号": get_bind_num,
        "登录账号": get_auth_num,
        "降价推送": get_price_sub_num,
    },
)
