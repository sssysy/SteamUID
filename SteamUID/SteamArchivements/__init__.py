from PIL import Image
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from ..utils.api import (
    get_archivement_info,
    get_archivement_schema,
    get_game_info,
)
from ..utils.exceptions import (
    SteamError,
    SteamRenderError,
    SteamValidationError,
)
from ..utils.PIL.draw import draw_archivement_info
from ..utils.utils import resolve_target_steamid64

SV = SV("steam成就服务")


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

    # 优先从 store API 获取中文名，GetPlayerAchievements 的 gameName 始终为英文
    try:
        game_info = await get_game_info(appid)
        game_name = (
            game_info.get("data", {}).get("name", "")
            if game_info and game_info.get("success")
            else ""
        )
    except Exception:
        game_name = ""
    game_name = game_name or playerstats.get("gameName", "") or appid

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


@SV.on_command("游戏成就")
async def game_archivements(bot: Bot, ev: Event):
    appid = ev.text.strip()
    try:
        if not appid:
            raise SteamValidationError("请携带appid！")
        steamid64 = await resolve_target_steamid64(ev)
        if not steamid64:
            raise SteamValidationError("请先绑定 steam 账号")

        data = await fetch_achievement_lists(appid, steamid64)
        img = await render_achievement_image(
            data["game_name"], data["unlocked"], data["locked"], steamid64
        )
        await bot.send(MessageSegment.image(img))

    except SteamError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[steamUID - 游戏成就] 未知错误 appid={appid}: {e!r}")
        await bot.send(f"发生未知错误: {e}")
