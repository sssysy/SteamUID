"""游戏标识解析：把用户输入的游戏名或 AppID 收敛成 appid，并给出确认文案。"""

import asyncio
from dataclasses import dataclass

from gsuid_core.logger import logger

from .config import api_base, store_base
from ..api.models import StoreBrowseItem, StoreSearchItem
from ..api.public import search_store, get_store_items
from ...steam_config import SteamConfig

_LANG = "schinese"
_TAG = "[Steam·游戏解析]"
_STORE_APP_TYPE_DLC = 4
_DETAIL_BATCH_SIZE = 50


@dataclass(frozen=True)
class GameRef:
    """解析出的目标游戏；exact 为 False 表示回落了搜索结果的首项。"""

    appid: str
    name: str
    exact: bool


def _candidates(items: list[StoreSearchItem]) -> list[StoreSearchItem]:
    """优先保留 app 候选；搜索异常时仍允许从带 id / name 的条目回落。"""
    apps = [item for item in items if "type" in item and item["type"] == "app" and "id" in item and "name" in item]
    if apps:
        return apps
    return [item for item in items if "id" in item and "name" in item]


def _exact_target(items: list[StoreSearchItem], raw: str) -> StoreSearchItem | None:
    normalized = raw.casefold()
    for item in items:
        if item["name"].casefold() == normalized:
            return item
    return None


async def _load_details(items: list[StoreSearchItem], *, cc: str) -> dict[str, StoreBrowseItem]:
    """一次批量取候选类型；无 Key 或接口失败时返回空表走名称匹配回退。"""
    keys = SteamConfig.get_config("SteamAPIKey").data
    if not keys:
        logger.debug(f"{_TAG} 未配置 Steam API Key，跳过 DLC 类型识别")
        return {}

    appids = [str(item["id"]) for item in items[:_DETAIL_BATCH_SIZE]]
    (result,) = await asyncio.gather(
        get_store_items(appids, lang=_LANG, cc=cc, key=keys[0], base_url=api_base()),
        return_exceptions=True,
    )
    if isinstance(result, BaseException):
        logger.warning(f"{_TAG} 批量详情获取失败: {type(result).__name__}")
        return {}

    details: dict[str, StoreBrowseItem] = {}
    for item in result:
        if "appid" in item:
            details[str(item["appid"])] = item
    return details


def _is_dlc(item: StoreSearchItem, details: dict[str, StoreBrowseItem]) -> bool | None:
    """返回 True / False；批量结果未覆盖该候选时返回 None。"""
    key = str(item["id"])
    if key not in details:
        return None
    detail = details[key]
    if "type" not in detail:
        return None
    return detail["type"] == _STORE_APP_TYPE_DLC


def _pick_target(
    items: list[StoreSearchItem],
    raw: str,
    *,
    allow_dlc: bool,
    details: dict[str, StoreBrowseItem],
) -> tuple[StoreSearchItem, bool]:
    exact = _exact_target(items, raw)
    if allow_dlc:
        if exact is not None:
            return exact, True
        return items[0], False

    if exact is not None and _is_dlc(exact, details) is True:
        raise ValueError(f"[{exact['name']}] 是 DLC，当前功能不匹配 DLC，请使用本体名称或 AppID")

    if exact is not None:
        return exact, True

    for item in items:
        if _is_dlc(item, details) is False:
            return item, False

    if details and all(_is_dlc(item, details) is True for item in items):
        raise ValueError(f"未找到与[{raw}]相关的本体游戏")
    return items[0], False


async def resolve_game_ref(query: str, *, cc: str, allow_dlc: bool = False) -> GameRef:
    """解析游戏标识；allow_dlc 控制名称搜索是否允许命中 DLC。"""
    raw = query.strip()
    if not raw:
        raise ValueError("请输入游戏名或 AppID，例如：steam游戏成就 730")
    if raw.isdigit():
        return GameRef(appid=raw, name=raw, exact=True)

    items: list[StoreSearchItem] = await search_store(raw, cc=cc, lang=_LANG, base_url=store_base())
    candidates = _candidates(items)
    if not candidates:
        raise ValueError(f"未找到与[{raw}]相关的游戏，请检查游戏名或改用 AppID")

    details = {} if allow_dlc else await _load_details(candidates, cc=cc)
    target, exact = _pick_target(candidates, raw, allow_dlc=allow_dlc, details=details)
    return GameRef(appid=str(target["id"]), name=target["name"], exact=exact)


def match_tip_text(ref: GameRef) -> str:
    """解析结果的确认文案；回落首项时明确说明未精确命中本体游戏。"""
    if ref.exact:
        return f"猜你想找 {ref.name}({ref.appid})，如有错误请使用 AppID 精确匹配游戏"
    return f"未精确匹配到本体游戏，已使用最接近的结果 {ref.name}({ref.appid})，如有错误请使用 AppID 精确匹配游戏"
