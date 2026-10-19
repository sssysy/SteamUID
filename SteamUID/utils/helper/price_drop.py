"""降价订阅的领域逻辑：订阅任务名、基线键、降价比对与基线编解码。

只做纯计算与编解码，不碰数据库、网络与渲染，便于直接单测。
"""

from typing import TypedDict

import msgspec

from ..api.models import PriceOverview

# 订阅行 uid 存 appid，查看与轮询都从这里取集合
SUBSCRIBE_TASK = "订阅Steam降价"
# 价格基线与轮询集合同表：任务名下键形如 price:{appid}
BASELINE_TASK = "降价轮询"

_BASELINE_PREFIX = "price:"


class PriceBaseline(TypedDict, total=False):
    """一条价格基线，只存比对与文案需要的字段。"""

    final: int
    currency: str
    discount_percent: int
    initial_formatted: str
    final_formatted: str


def baseline_key(appid: str) -> str:
    return f"{_BASELINE_PREFIX}{appid}"


def appid_of_key(key: str) -> str | None:
    """基线键里的 appid；非 price: 前缀返回 None。"""
    if not key.startswith(_BASELINE_PREFIX):
        return None
    return key[len(_BASELINE_PREFIX) :]


def to_baseline(overview: PriceOverview) -> PriceBaseline:
    """从 price_overview 提取基线字段，缺失字段不进基线。"""
    baseline = PriceBaseline()
    if "final" in overview:
        baseline["final"] = overview["final"]
    if "currency" in overview:
        baseline["currency"] = overview["currency"]
    if "discount_percent" in overview:
        baseline["discount_percent"] = overview["discount_percent"]
    if "initial_formatted" in overview:
        baseline["initial_formatted"] = overview["initial_formatted"]
    if "final_formatted" in overview:
        baseline["final_formatted"] = overview["final_formatted"]
    return baseline


def baseline_to_json(baseline: PriceBaseline) -> str:
    return msgspec.json.encode(baseline).decode()


def baseline_from_json(raw: str) -> PriceBaseline:
    """解析基线 JSON；结构非法时抛 msgspec.ValidationError。"""
    return msgspec.json.decode(raw, type=PriceBaseline)


def is_drop(previous: PriceBaseline | None, current: PriceBaseline) -> bool:
    """相对基线降价：两侧都有 final 且现值更低才算，缺基线不通知。"""
    if previous is None:
        return False
    if "final" not in previous or "final" not in current:
        return False
    return current["final"] < previous["final"]


def price_text(baseline: PriceBaseline) -> str:
    """现价文案：优先接口下发的格式化串，缺失时按货币符号与分值拼。"""
    if "final_formatted" in baseline and baseline["final_formatted"]:
        return baseline["final_formatted"]
    currency = baseline["currency"] if "currency" in baseline else ""
    final = baseline["final"] if "final" in baseline else 0
    return f"{currency} {final / 100:.2f}"


def discount_label(percent: int) -> str:
    """折扣文案：25% 优惠显示 75折，20% 优惠显示 8折。"""
    remaining = 100 - percent
    if remaining % 10 == 0:
        return f"{remaining // 10}折"
    return f"{remaining}折"
