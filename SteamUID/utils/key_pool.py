"""Steam Web API Key 池：每日用量记账、429 冷却与轮换选取。

与具体接口无关：调用方给出 Key 列表与一次请求动作，本模块负责选 Key 与换 Key 重试。
"""

import datetime
from typing import TypeVar
from threading import Lock
from collections import defaultdict
from collections.abc import Callable, Sequence, Awaitable

import httpx

from gsuid_core.logger import logger

_T = TypeVar("_T")

# 单 Key 每日调用硬上限，达到后跳过
DAILY_BUDGET = 50000
# 429 惩罚计数，降低该 Key 后续被选中的概率
LIMIT_PENALTY = 1000
# 429 换 Key 的最大尝试次数
MAX_ATTEMPTS = 3

_lock = Lock()
_usage: defaultdict[str, int] = defaultdict(int)
_cooldown_until: defaultdict[str, float] = defaultdict(float)
_usage_date: str = ""


def normalize_keys(raw: Sequence[str]) -> list[str]:
    """去空白、去重、丢弃空串，保持原顺序。"""
    keys: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def has_api_key(raw: Sequence[str]) -> bool:
    """池中是否至少存在一个非空 Key。"""
    return bool(normalize_keys(raw))


def _ensure_day() -> None:
    """跨天清空记账，避免昨日用量与冷却拖到今天。"""
    global _usage_date
    today = datetime.date.today().isoformat()
    if _usage_date != today:
        _usage.clear()
        _cooldown_until.clear()
        _usage_date = today


def _mask(key: str) -> str:
    if len(key) > 9:
        return f"{key[:5]}...{key[-4:]}"
    return "***"


def get_api_key(raw: Sequence[str]) -> str:
    """选今日用量最少且未冷却、未达硬上限的 Key；池为空返回空串。"""
    _ensure_day()
    keys = normalize_keys(raw)
    if not keys:
        return ""

    now = datetime.datetime.now().timestamp()
    with _lock:
        available = [key for key in keys if _cooldown_until[key] <= now and _usage[key] < DAILY_BUDGET]
        if available:
            selected = min(available, key=lambda item: _usage[item])
        else:
            cooled = [key for key in keys if _cooldown_until[key] > now]
            if cooled:
                selected = min(cooled, key=lambda item: _cooldown_until[item])
                logger.warning(f"[Steam·密钥池] Key 均在冷却中，临时使用即将恢复的 Key: {_mask(selected)}")
            else:
                selected = min(keys, key=lambda item: _usage[item])
                logger.warning(
                    f"[Steam·密钥池] Key 均已达每日硬上限 {DAILY_BUDGET}，仍使用用量最少的 Key: {_mask(selected)}"
                )

        _usage[selected] += 1
        return selected


def mark_key_limited(key: str, cooldown_seconds: int) -> None:
    """标记 Key 触发 429：进入冷却并追加惩罚用量。"""
    if not key:
        return

    _ensure_day()
    now = datetime.datetime.now().timestamp()
    with _lock:
        _cooldown_until[key] = now + cooldown_seconds
        _usage[key] += LIMIT_PENALTY
    logger.warning(f"[Steam·密钥池] API Key 触发 429，冷却 {cooldown_seconds}s: {_mask(key)}")


async def request_with_api_key(
    do_request: Callable[[str], Awaitable[_T]],
    raw: Sequence[str],
    *,
    cooldown_seconds: int,
    preferred_key: str = "",
    max_attempts: int = MAX_ATTEMPTS,
) -> _T:
    """按池取 Key 发请求；遇到 429 换下一个 Key，最多尝试 max_attempts 次。

    preferred_key 只用于首次尝试，不重复计入池用量（调用方通常已从池中取出）。
    """
    keys = normalize_keys(raw)
    last_error: httpx.HTTPStatusError | None = None
    used_preferred = False

    for _ in range(max(1, max_attempts)):
        if preferred_key and not used_preferred:
            key = preferred_key
            used_preferred = True
        else:
            key = get_api_key(keys)

        try:
            return await do_request(key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429:
                raise
            last_error = e
            mark_key_limited(key, cooldown_seconds)

    if last_error is None:
        raise RuntimeError("Steam API Key 池不可用")
    raise last_error
