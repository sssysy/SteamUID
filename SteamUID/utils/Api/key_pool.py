"""Steam Web API Key 池：用量记账、429 冷却与选取"""
import datetime
from collections.abc import Awaitable, Callable
from threading import Lock

import httpx
from gsuid_core.logger import logger

from ...SteamConfig import SteamConfig

# 单 Key 每日调用硬上限，达到后跳过
DAILY_BUDGET = 50000
# 429 惩罚额外计数，降低后续被选中概率
LIMIT_PENALTY = 1000
# 429 换 Key 最大尝试次数（含首次）
MAX_ATTEMPTS = 3

_lock = Lock()
_usage: dict[str, int] = {}
_cooldown_until: dict[str, float] = {}
_usage_date: str = ""


def _today() -> str:
    return datetime.date.today().isoformat()


def _ensure_day() -> None:
    global _usage_date
    today = _today()
    if _usage_date != today:
        _usage.clear()
        _cooldown_until.clear()
        _usage_date = today


def _pool_keys() -> list[str]:
    raw = SteamConfig.get_config("SteamWebAPIKey").data
    if not isinstance(raw, list):
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _mask(key: str) -> str:
    if len(key) > 9:
        return f"{key[:5]}...{key[-4:]}"
    return "***"


def _cooldown_seconds() -> int:
    try:
        return int(SteamConfig.get_config("KeyPool429Cooldown").data or 600)
    except Exception:
        return 600


def has_api_key() -> bool:
    return bool(_pool_keys())


def get_api_key() -> str:
    """选取今日用量最少且未冷却、未达硬上限的 Key；池为空返回空串。"""
    _ensure_day()
    keys = _pool_keys()
    if not keys:
        return ""

    now = datetime.datetime.now().timestamp()
    with _lock:
        available = [
            key
            for key in keys
            if _cooldown_until.get(key, 0) <= now
            and _usage.get(key, 0) < DAILY_BUDGET
        ]
        if available:
            selected = min(available, key=lambda k: _usage.get(k, 0))
        else:
            cooled = [k for k in keys if _cooldown_until.get(k, 0) > now]
            if cooled:
                selected = min(cooled, key=lambda k: _cooldown_until.get(k, 0))
                logger.warning(
                    f"[SteamUID] API Key 池均在冷却中，临时使用即将恢复的 Key: {_mask(selected)}"
                )
            else:
                selected = min(keys, key=lambda k: _usage.get(k, 0))
                logger.warning(
                    f"[SteamUID] API Key 池均已达到每日硬上限 {DAILY_BUDGET}，"
                    f"仍使用用量最少的 Key: {_mask(selected)}"
                )
        _usage[selected] = _usage.get(selected, 0) + 1
        return selected


def mark_key_limited(key: str) -> None:
    """标记 Key 触发 429：进入冷却并加惩罚计数。"""
    if not key:
        return
    _ensure_day()
    cooldown = _cooldown_seconds()
    now = datetime.datetime.now().timestamp()
    with _lock:
        _cooldown_until[key] = now + cooldown
        _usage[key] = _usage.get(key, 0) + LIMIT_PENALTY
    logger.warning(f"[SteamUID] API Key 触发 429，冷却 {cooldown}s: {_mask(key)}")


async def request_with_api_key(
    do_request: Callable[[str], Awaitable[httpx.Response]],
    *,
    preferred_key: str = "",
    max_attempts: int = MAX_ATTEMPTS,
) -> httpx.Response | None:
    """按池取 Key 发起请求；429 时标记并换下一 Key，最多 max_attempts 次。

    preferred_key 仅作首次尝试，不重复计入池用量（调用方通常已从池取出）。
    """
    response: httpx.Response | None = None
    used_preferred = False
    for _ in range(max(1, max_attempts)):
        if preferred_key and not used_preferred:
            key = preferred_key
            used_preferred = True
        else:
            key = get_api_key()
        if not key:
            if response is None:
                response = await do_request("")
            break
        response = await do_request(key)
        if response.status_code == 429:
            mark_key_limited(key)
            continue
        return response
    return response
