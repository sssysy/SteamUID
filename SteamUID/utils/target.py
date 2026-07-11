from gsuid_core.models import Event

from .utils import auto2steamid64
from .database.models import SteamBind
from ..SteamConfig import SteamConfig
from .exceptions import SteamValidationError


async def resolve_target_steamid64(ev: Event, text: str = "") -> str | None:
    """三级回退：auto2steamid64(text) → @他人的主ID → 当前用户的主ID。
    注意：会修改 ev.user_id 以支持 @他人。
    """
    if ev.at:
        if not SteamConfig.get_config("AllowAt").data:
            raise SteamValidationError("未开启 @ 他人获取他人信息功能")
        ev.user_id = ev.at

    if text:
        steamid64 = auto2steamid64(text.strip())
        if steamid64:
            return steamid64

    return await SteamBind.get_main_id(
        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
    )
