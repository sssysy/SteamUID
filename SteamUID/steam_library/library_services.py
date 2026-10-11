"""游戏墙：拉取资料与游戏库、解析封面，最后渲染出图。"""

from ..steam_config import (
    get_allow_griddb_cover,
    get_api_keys,
    get_griddb_key,
    get_key_cooldown,
)
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.helper.library import LibraryGame, visible_games
from ..utils.helper.profile import load_profile_assets
from ..utils.helper.steam_api import fetch_owned_games
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.static_assets import get_default_avatar_url, get_img_cache_url
from ..utils.render.html.wall import WallGame, render_game_wall


async def build_game_wall(steamid64: str) -> bytes:
    """出图入口：资料 -> 游戏库 -> 封面 -> 渲染。"""
    keys = get_api_keys()
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    profile = await load_profile_assets(steamid64)
    payload = await fetch_owned_games(
        steamid64, keys=keys, cooldown=get_key_cooldown()
    )

    if "games" not in payload:
        raise ValueError("未能获取该账号的游戏库，可能资料未公开或暂无游戏")

    library: list[LibraryGame] = []
    for game in payload["games"]:
        if "appid" not in game:
            continue
        library.append(
            LibraryGame(
                appid=str(game["appid"]),
                name=game["name"] if "name" in game else "",
                playtime_minutes=(
                    game["playtime_forever"] if "playtime_forever" in game else 0
                ),
            )
        )

    played = visible_games(library)
    if not played:
        raise ValueError("该 steam 账号暂无可展示的游戏（需游玩时长 ≥ 10 分钟）")

    griddb_key = get_griddb_key() if get_allow_griddb_cover() else ""
    covers = await resolve_cover_names(
        [game.appid for game in played], country="", griddb_key=griddb_key
    )

    wall_games = [
        WallGame(
            name=game.name,
            playtime_minutes=game.playtime_minutes,
            cover_url=get_img_cache_url(covers[game.appid]) if game.appid in covers else "",
        )
        for game in played
    ]
    user = PillAccount(
        name=profile.name,
        friend_code=profile.friend_code,
        avatar_url=get_img_cache_url(profile.avatar_name) or get_default_avatar_url(),
        frame_url=get_img_cache_url(profile.frame_name),
        background_url=get_img_cache_url(profile.background_name),
    )
    return await render_game_wall(user, wall_games)
