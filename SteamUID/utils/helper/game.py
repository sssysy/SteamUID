"""游戏标识解析：把用户输入的游戏名或 AppID 收敛成 appid，并给出确认文案。"""

from dataclasses import dataclass

from ..api.models import StoreSearchItem
from ..api.public import search_store

_LANG = "schinese"


@dataclass(frozen=True)
class GameRef:
    """解析出的目标游戏；exact 为 False 表示回落了搜索结果的首项。"""

    appid: str
    name: str
    exact: bool


def _pick_target(items: list[StoreSearchItem]) -> StoreSearchItem | None:
    """取首个带 id / name 的本体游戏，避免匹配到 package 与 bundle。"""
    for item in items:
        if "type" not in item or item["type"] != "app":
            continue
        if "id" in item and "name" in item:
            return item
    return None


async def resolve_game_ref(query: str, *, cc: str) -> GameRef:
    """解析游戏标识：纯数字直接当 appid，否则走商店搜索。"""
    raw = query.strip()
    if not raw:
        raise ValueError("请输入游戏名或 AppID，例如：steam游戏成就 730")
    if raw.isdigit():
        return GameRef(appid=raw, name=raw, exact=True)

    items: list[StoreSearchItem] = await search_store(raw, cc=cc, lang=_LANG)
    if not items:
        raise ValueError(f"未找到与[{raw}]相关的游戏，请检查游戏名或改用 AppID")

    target = _pick_target(items)
    exact = target is not None
    if target is None:
        target = items[0]
    if "id" not in target:
        raise ValueError(f"未找到与[{raw}]相关的游戏，请检查游戏名或改用 AppID")
    name = target["name"] if "name" in target else raw
    return GameRef(appid=str(target["id"]), name=name, exact=exact)


def match_tip_text(ref: GameRef) -> str:
    """解析结果的确认文案；回落首项时明确说明未精确命中本体游戏。"""
    if ref.exact:
        return f"猜你想找 {ref.name}({ref.appid})，如有错误请使用 AppID 精确匹配游戏"
    return f"未精确匹配到本体游戏，已使用最接近的结果 {ref.name}({ref.appid})，如有错误请使用 AppID 精确匹配游戏"
