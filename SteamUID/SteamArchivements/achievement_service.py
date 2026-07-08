from PIL import Image

from ..utils.api import (
    get_archivement_info,
    get_archivement_schema,
)
from ..utils.exceptions import SteamValidationError, SteamRenderError
from ..utils.PIL.draw import draw_archivement_info


async def fetch_achievement_lists(appid: str, steamid64: str) -> dict:
    playerstats = await get_archivement_info(appid, steamid64)

    achievements = playerstats.get("achievements")
    if not achievements:
        raise SteamValidationError(
            "未获取到成就数据，可能该游戏无成就或 steam 资料未公开"
        )

    schema_list = await get_archivement_schema(appid)
    schema_map = {s.get("name"): s for s in schema_list}

    unlocked_list: list[tuple[str, str, str]] = []
    locked_list: list[tuple[str, str, str]] = []
    for ach in achievements:
        apiname = ach.get("apiname", "")
        achieved = ach.get("achieved") == 1
        s = schema_map.get(apiname, {})
        # 已解锁用 icon，未解锁用 icongray
        icon_url = s.get("icon", "") if achieved else s.get("icongray", "")
        name = ach.get("name") or s.get("displayName", "") or apiname
        desc = ach.get("description") or s.get("description", "") or ""
        if achieved:
            unlocked_list.append((icon_url, name, desc))
        else:
            locked_list.append((icon_url, name, desc))

    if not unlocked_list and not locked_list:
        raise SteamValidationError("该游戏暂无成就数据")

    game_name = playerstats.get("gameName", "") or appid

    return {
        "unlocked": unlocked_list,
        "locked": locked_list,
        "game_name": game_name,
    }


async def render_achievement_image(
    game_name: str,
    unlocked_list: list[tuple[str, str, str]],
    locked_list: list[tuple[str, str, str]],
    steamid64: str,
) -> Image.Image:
    try:
        img = await draw_archivement_info(game_name, unlocked_list, locked_list)
    except Exception as e:
        raise SteamRenderError(f"成就图片渲染失败: {e}") from e

    return img
