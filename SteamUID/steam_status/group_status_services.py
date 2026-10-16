"""steam群友状态：本群已绑定群友的实时在线与游戏状态列表。"""

import asyncio
from dataclasses import dataclass
from collections.abc import Mapping, Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..steam_config import SteamConfig
from .status_services import PERSONA_TEXT
from ..utils.api.models import PlayerSummary
from ..utils.helper.bind import session_ids
from ..utils.helper.config import region_cc, region_lang, griddb_cover_key
from ..utils.helper.profile import load_mini_background_name, load_initiator_card_background_name
from ..utils.helper.ranking import load_group_members
from ..utils.helper.steam_api import fetch_player_summaries
from ..utils.helper.game_cover import resolve_cover_name
from ..utils.database.model_bind import SteamBind
from ..utils.render.html.account_pill import PillAccount
from ..utils.render.html.group_status import render_group_status
from ..utils.render.html.static_assets import get_img_cache_url, resolve_card_bg_url, get_default_avatar_url

_TAG = "[Steam·群友状态]"

# 一张卡片最多展示的人数，超出只在尾部提示还有更多
_MAX_MEMBERS = 10
_NO_MEMBER = "本群当前暂无在线或正在玩游戏的群友"


@dataclass(frozen=True)
class _ActiveAccount:
    """一个用户的活跃账号：绑定归属、状态文案与色调、正在玩的 appid。"""

    user_id: str
    steamid64: str
    status_text: str
    status_tone: str
    appid: str


def _presence(player: PlayerSummary) -> tuple[str, str] | None:
    """返回 (状态文案, 色调)；离线返回 None，personastate 取值未知时按在线处理。"""
    game_id = player["gameid"] if "gameid" in player else ""
    if game_id:
        title = player["gameextrainfo"] if "gameextrainfo" in player else ""
        return (f"游戏中：{title}" if title else "游戏中"), "ingame"

    state = player["personastate"] if "personastate" in player else 0
    if state == 0:
        return None
    return (PERSONA_TEXT[state] if state in PERSONA_TEXT else "在线"), "online"


def _grouped_binds(binds: Sequence[SteamBind]) -> list[list[SteamBind]]:
    """按用户分组绑定，保持绑定表里的首次出现顺序。"""
    grouped: dict[str, list[SteamBind]] = {}
    for bind in binds:
        if bind.user_id in grouped:
            grouped[bind.user_id].append(bind)
        else:
            grouped[bind.user_id] = [bind]
    return list(grouped.values())


def _pick_active(binds: Sequence[SteamBind], summaries: Mapping[str, PlayerSummary]) -> _ActiveAccount | None:
    """取该用户优先展示的活跃账号：主账号活跃时用主账号，否则用首个活跃账号。"""
    fallback: _ActiveAccount | None = None
    for bind in binds:
        player = summaries[bind.steamid64] if bind.steamid64 in summaries else None
        if player is None:
            continue
        presence = _presence(player)
        if presence is None:
            continue
        status_text, status_tone = presence
        account = _ActiveAccount(
            user_id=bind.user_id,
            steamid64=bind.steamid64,
            status_text=status_text,
            status_tone=status_tone,
            appid=player["gameid"] if "gameid" in player else "",
        )
        if bind.is_main_id:
            return account
        if fallback is None:
            fallback = account
    return fallback


def _active_accounts(binds: Sequence[SteamBind], summaries: Mapping[str, PlayerSummary]) -> list[_ActiveAccount]:
    """挑出全部活跃用户，游戏中置顶，其余保持绑定表顺序。"""
    actives: list[_ActiveAccount] = []
    for user_binds in _grouped_binds(binds):
        account = _pick_active(user_binds, summaries)
        if account is not None:
            actives.append(account)
    actives.sort(key=lambda account: 0 if account.status_tone == "ingame" else 1)
    return actives


async def _background_url(account: _ActiveAccount, *, country: str, lang: str, griddb_key: str) -> str:
    """背景直链：游戏中用游戏封面，在线用迷你资料背景；取不到留空串。"""
    if account.appid:
        name = await resolve_cover_name(account.appid, country=country, lang=lang, griddb_key=griddb_key)
    else:
        name = await load_mini_background_name(account.steamid64)
    return get_img_cache_url(name)


def _safe_background(account: _ActiveAccount, loaded: str | BaseException) -> str:
    """背景解析失败只记日志并留空串，不影响药丸本体。"""
    if isinstance(loaded, BaseException):
        logger.warning(f"{_TAG} 背景获取失败 {account.steamid64}: {loaded!r}")
        return ""
    return loaded


async def _member_pill(
    account: _ActiveAccount,
    group_id: str,
    background_url: str,
) -> PillAccount:
    """把活跃账号补成药丸数据：群名片与头像来自 QQ，背景由调用方解析。"""
    member = (await load_group_members(group_id, [account.user_id]))[account.user_id]
    return PillAccount(
        name=member.name,
        friend_code="",
        avatar_url=get_img_cache_url(member.avatar_name) or get_default_avatar_url(),
        frame_url="",
        background_url=background_url,
        status_text=account.status_text,
        status_tone=account.status_tone,
    )


async def build_group_status_image(ev: Event) -> bytes:
    """出图入口：取本群绑定 → 批量摘要 → 挑活跃账号 → 补资料与背景 → 渲染。"""
    if not ev.group_id:
        raise ValueError("请在群聊中使用此功能")

    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        raise ValueError("请先配置 Steam API Key")

    bot_id, bot_self_id, group_id = session_ids(ev)
    binds = await SteamBind.get_binds_by_group(bot_id, bot_self_id, group_id)
    if not binds:
        raise ValueError(_NO_MEMBER)

    steamids = list(dict.fromkeys(bind.steamid64 for bind in binds))
    players = await fetch_player_summaries(steamids, keys=keys, cooldown=SteamConfig.get_config("KeyPoolCooldown").data)
    summaries = {player["steamid"]: player for player in players if "steamid" in player}

    actives = _active_accounts(binds, summaries)
    if not actives:
        raise ValueError(_NO_MEMBER)

    country = region_cc()
    lang = region_lang()
    griddb_key = griddb_cover_key()
    shown = actives[:_MAX_MEMBERS]
    loaded, card_bg_name = await asyncio.gather(
        asyncio.gather(
            *(_background_url(account, country=country, lang=lang, griddb_key=griddb_key) for account in shown),
            return_exceptions=True,
        ),
        load_initiator_card_background_name(ev),
    )
    backgrounds = [_safe_background(account, item) for account, item in zip(shown, loaded)]
    pills = await asyncio.gather(
        *(_member_pill(account, group_id, background) for account, background in zip(shown, backgrounds))
    )
    return await render_group_status(
        list(pills),
        has_more=len(actives) > _MAX_MEMBERS,
        card_bg_url=resolve_card_bg_url(card_bg_name),
    )
