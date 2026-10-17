"""steam好友状态：目标账号在线好友的药丸列表。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Mapping, Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from .status_services import PERSONA_TEXT
from ..utils.api.models import FriendEntry, PlayerSummary
from ..utils.downloader import download
from ..utils.helper.bind import get_main_steamid64
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.command import resolve_target
from ..utils.helper.profile import load_card_background_name, load_mini_background_name
from ..utils.helper.steam_api import fetch_friend_list, fetch_player_summaries
from ..utils.helper.game_cover import resolve_cover_names
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.group_status import render_group_status
from ..utils.render.html.static_assets import (
    get_img_cache_url,
    resolve_card_bg_url,
    get_default_avatar_url,
)

_TAG = "[Steam·好友状态]"
# 一张卡片最多展示 30 人（两列 x 15 行）
_MAX_FRIENDS = 30
# 迷你资料背景逐人请求，限制并发避免一次打太多
_MINI_BG_CONCURRENCY = 5


@dataclass(frozen=True)
class _OnlineFriend:
    """在线好友的展示数据；rank 只用于稳定分组排序。"""

    steamid64: str
    name: str
    avatar_url: str
    status_text: str
    status_tone: str
    appid: str
    rank: int


def _presence(player: PlayerSummary) -> tuple[int, str, str, str] | None:
    """返回 (分组, 状态文案, 色调, appid)；离线返回 None。"""
    game_id = player["gameid"] if "gameid" in player else ""
    if game_id:
        title = player["gameextrainfo"] if "gameextrainfo" in player else ""
        return 0, f"游戏中：{title}" if title else "游戏中", "ingame", game_id

    state = player["personastate"] if "personastate" in player else 0
    if state == 0:
        return None
    text = PERSONA_TEXT[state] if state in PERSONA_TEXT else "在线"
    if state in (3, 4):
        return 2, text, "away", ""
    return 1, text, "online", ""


def _avatar_url(player: PlayerSummary) -> str:
    """取药丸尺寸足够的头像直链；缺失时返回空串。"""
    if "avatarmedium" in player and player["avatarmedium"]:
        return player["avatarmedium"]
    if "avatar" in player:
        return player["avatar"]
    return ""


def _online_friends(
    friends: Sequence[FriendEntry],
    summaries: Mapping[str, PlayerSummary],
) -> list[_OnlineFriend]:
    """按好友列表原顺序收集在线好友，再按分组做稳定排序。"""
    entries: list[_OnlineFriend] = []
    for friend in friends:
        if "steamid" not in friend:
            continue
        steamid64 = friend["steamid"]
        if steamid64 not in summaries:
            continue
        player = summaries[steamid64]
        presence = _presence(player)
        if presence is None:
            continue
        rank, status_text, status_tone, appid = presence
        entries.append(
            _OnlineFriend(
                steamid64=steamid64,
                name=player["personaname"] if "personaname" in player else "",
                avatar_url=_avatar_url(player),
                status_text=status_text,
                status_tone=status_tone,
                appid=appid,
                rank=rank,
            )
        )
    entries.sort(key=lambda item: item.rank)
    return entries


async def _mini_background_name(friend: _OnlineFriend, sem: asyncio.Semaphore) -> str:
    """取在线 / 离开好友的迷你资料背景文件名；游戏中的人物不走这里。"""
    if friend.rank == 0:
        return ""
    async with sem:
        return await load_mini_background_name(friend.steamid64)


async def _build_pills(
    shown: Sequence[_OnlineFriend],
    *,
    country: str,
    lang: str,
    griddb_key: str,
    card_steamid64: str,
) -> tuple[list[PillAccount], str]:
    """并发补齐头像 / 游戏封面 / 迷你背景，返回药丸数据与卡片底图。"""
    appids = list(dict.fromkeys(friend.appid for friend in shown if friend.appid))
    avatar_urls = [friend.avatar_url for friend in shown]
    sem = asyncio.Semaphore(_MINI_BG_CONCURRENCY)

    covers, avatar_paths, mini_results, card_bg_name = await asyncio.gather(
        resolve_cover_names(appids, country=country, lang=lang, griddb_key=griddb_key),
        download(avatar_urls, kind="image"),
        asyncio.gather(*(_mini_background_name(friend, sem) for friend in shown), return_exceptions=True),
        load_card_background_name(card_steamid64),
    )

    pills: list[PillAccount] = []
    for friend, avatar_path, mini_result in zip(shown, avatar_paths, mini_results):
        if isinstance(mini_result, BaseException):
            logger.warning(f"{_TAG} 迷你背景获取失败 {friend.steamid64}: {type(mini_result).__name__}")
            mini_name = ""
        else:
            mini_name = mini_result

        if friend.rank == 0:
            background_name = covers[friend.appid] if friend.appid in covers else ""
        else:
            background_name = mini_name

        avatar_url = get_img_cache_url(avatar_path.name) if avatar_path is not None else ""
        pills.append(
            PillAccount(
                name=friend.name,
                friend_code="",
                avatar_url=avatar_url or get_default_avatar_url(),
                frame_url="",
                background_url=get_img_cache_url(background_name),
                status_text=friend.status_text,
                status_tone=friend.status_tone,
            )
        )
    return pills, resolve_card_bg_url(card_bg_name)


async def build_friend_status_image(ev: Event) -> bytes:
    """出图入口：好友列表 → 批量摘要 → 在线筛选与分组 → 素材 → 渲染。"""
    user_id, steamid64 = await resolve_target(ev, allow_at=SteamConfig.get_config("AllowAt").data)
    if steamid64 is None:
        steamid64 = await get_main_steamid64(ev, user_id)
    if steamid64 is None:
        raise ValueError("请先绑定 steam 账号")

    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")
    cooldown = SteamConfig.get_config("KeyPoolCooldown").data

    friends = await fetch_friend_list(steamid64, keys=keys, cooldown=cooldown)
    if not friends:
        raise ValueError("该账号好友列表未公开，或没有好友")

    friend_ids = list(dict.fromkeys(friend["steamid"] for friend in friends if "steamid" in friend))
    players = await fetch_player_summaries(friend_ids, keys=keys, cooldown=cooldown)
    summaries = {player["steamid"]: player for player in players if "steamid" in player}

    online = _online_friends(friends, summaries)
    if not online:
        raise ValueError("当前没有在线好友")

    shown = online[:_MAX_FRIENDS]
    remaining = len(online) - len(shown)
    pills, card_bg_url = await _build_pills(
        shown,
        country=region_cc(),
        lang=region_lang(),
        griddb_key=griddb_cover_key(),
        card_steamid64=steamid64,
    )
    more_text = f"还有 {remaining} 位在线好友未展示" if remaining > 0 else ""
    return await render_group_status(
        pills,
        title="steam好友状态",
        more_text=more_text,
        card_bg_url=card_bg_url,
    )
