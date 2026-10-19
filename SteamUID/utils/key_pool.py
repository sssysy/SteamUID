"""Steam Web API Key 池：每日用量记账、429 冷却、被拒废弃与轮换选取。

与具体接口无关：调用方给出 Key 列表与一次请求动作，本模块负责选 Key 与换 Key 重试。
401 立即废弃；403 达到重试上限后废弃，避免临时抖动误伤。
"""

import datetime
from typing import TypeVar
from threading import Lock
from collections import defaultdict
from collections.abc import Callable, Sequence, Awaitable

import httpx

from gsuid_core.logger import logger
from gsuid_core.utils.message import send_msg_to_master

_T = TypeVar("_T")

# 单 Key 每日调用硬上限，达到后跳过
DAILY_BUDGET = 50000
# 429 惩罚计数，降低该 Key 后续被选中的概率
LIMIT_PENALTY = 1000
# 池内无可选 Key 时的用户可见提示
_NO_KEY_HINT = "请先配置 Steam API Key"
_EXHAUSTED_HINT = "Steam API Key 均失效，请检查配置"

_lock = Lock()
_usage: defaultdict[str, int] = defaultdict(int)
_cooldown_until: defaultdict[str, float] = defaultdict(float)
_usage_date: str = ""
# 进程内废弃的 Key：跨天不清，只随重启 / 插件重载清空
_abandoned: set[str] = set()
# 403 连续失败计数：成功或切换异常后清零，达到重试上限才废弃
_forbidden_failures: defaultdict[str, int] = defaultdict(int)
# 全废私信只发一次，与废弃集合同生命周期
_all_dead_notified: bool = False


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


def has_available_api_key(raw: Sequence[str]) -> bool:
    """池中是否存在未废弃 Key；冷却与每日额度不计入判断。"""
    keys = normalize_keys(raw)
    if not keys:
        return False
    with _lock:
        return any(key not in _abandoned for key in keys)


def _ensure_day() -> None:
    """跨天清空记账，避免昨日用量与冷却拖到今天；废弃集合不随之清空。"""
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


def _tail(key: str) -> str:
    """Key 尾号；只用于私信主人，不泄露完整 Key。"""
    return key[-4:]


def get_api_key(raw: Sequence[str]) -> str:
    """选今日用量最少且未冷却、未达硬上限、未被废弃的 Key；无可选返回空串。"""
    _ensure_day()
    keys = normalize_keys(raw)
    if not keys:
        return ""

    now = datetime.datetime.now().timestamp()
    with _lock:
        remaining = [key for key in keys if key not in _abandoned]
        if not remaining:
            return ""

        available = [key for key in remaining if _cooldown_until[key] <= now and _usage[key] < DAILY_BUDGET]
        if available:
            selected = min(available, key=lambda item: _usage[item])
        else:
            cooled = [key for key in remaining if _cooldown_until[key] > now]
            if cooled:
                selected = min(cooled, key=lambda item: _cooldown_until[item])
                logger.warning(f"[Steam·密钥池] Key 均在冷却中，临时使用即将恢复的 Key: {_mask(selected)}")
            else:
                selected = min(remaining, key=lambda item: _usage[item])
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
        if key in _forbidden_failures:
            del _forbidden_failures[key]
    logger.warning(f"[Steam·密钥池] API Key 触发 429，冷却 {cooldown_seconds}s: {_mask(key)}")


def mark_key_invalid(key: str) -> None:
    """标记 Key 被 Steam 拒绝：本进程内废弃，不再参与选取。"""
    if not key:
        return

    with _lock:
        _abandoned.add(key)
        if key in _forbidden_failures:
            del _forbidden_failures[key]
    logger.warning(f"[Steam·密钥池] API Key 被拒绝，本进程内废弃: {_mask(key)}")


def _clear_forbidden_failures(key: str) -> None:
    with _lock:
        if key in _forbidden_failures:
            del _forbidden_failures[key]


def _record_forbidden(key: str, limit: int) -> None:
    """累计连续 403；达到 limit 时废弃该 Key。"""
    with _lock:
        failures = _forbidden_failures[key] + 1
        if failures < limit:
            _forbidden_failures[key] = failures
            return
        _abandoned.add(key)
        if key in _forbidden_failures:
            del _forbidden_failures[key]
    logger.warning(f"[Steam·密钥池] API Key 连续 403 达到 {limit} 次，本进程内废弃: {_mask(key)}")


def _key_retry_count() -> int:
    """读取用户配置的额外重试次数；0 表示只发首次请求。"""
    from ..steam_config import SteamConfig

    return max(0, SteamConfig.get_config("KeyRetryCount").data)


def _notify_enabled() -> bool:
    """读全废私信开关；延迟 import 避免 utils 反向依赖 steam_config。"""
    from ..steam_config import SteamConfig

    return bool(SteamConfig.get_config("NotifyKeyExhausted").data)


async def _notify_all_exhausted(keys: Sequence[str]) -> None:
    """池内 Key 全部废弃时私信主人一次；开关关闭或仍有可选 Key 时不动。"""
    global _all_dead_notified
    if not keys or _all_dead_notified or not _notify_enabled():
        return

    with _lock:
        if _all_dead_notified or any(key not in _abandoned for key in keys):
            return
        _all_dead_notified = True

    tails = "、".join(f"尾号 {_tail(key)}" for key in keys)
    await send_msg_to_master(f"[Steam] 所有 API Key 均已失效，已停止使用：{tails}。请检查配置。")


async def request_with_api_key(
    do_request: Callable[[str], Awaitable[_T]],
    raw: Sequence[str],
    *,
    cooldown_seconds: int,
    preferred_key: str = "",
    retry_count: int | None = None,
) -> _T:
    """按池取 Key 发请求；403 / 429 按配置重试，401 立即废弃。

    preferred_key 只用于首次尝试，不重复计入池用量（调用方通常已从池中取出）。
    retry_count 为空时读取用户配置；0 表示只发首次请求。
    """
    keys = normalize_keys(raw)
    if not keys:
        raise ValueError(_NO_KEY_HINT)

    retries = _key_retry_count() if retry_count is None else retry_count
    retries = max(0, retries)
    forbidden_limit = retries + 1
    last_error: httpx.HTTPStatusError | None = None
    used_preferred = False

    for _ in range(retries + 1):
        if preferred_key and not used_preferred and preferred_key not in _abandoned:
            key = preferred_key
            used_preferred = True
        else:
            key = get_api_key(keys)

        if not key:
            await _notify_all_exhausted(keys)
            raise ValueError(_EXHAUSTED_HINT)

        try:
            result = await do_request(key)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == httpx.codes.UNAUTHORIZED:
                last_error = e
                mark_key_invalid(key)
                await _notify_all_exhausted(keys)
                continue
            if status == httpx.codes.FORBIDDEN:
                last_error = e
                _record_forbidden(key, forbidden_limit)
                await _notify_all_exhausted(keys)
                continue
            if status == httpx.codes.TOO_MANY_REQUESTS:
                last_error = e
                mark_key_limited(key, cooldown_seconds)
                continue
            _clear_forbidden_failures(key)
            raise
        _clear_forbidden_failures(key)
        return result

    if last_error is None:
        raise RuntimeError("Steam API Key 池不可用")
    if not has_available_api_key(keys):
        await _notify_all_exhausted(keys)
        raise ValueError(_EXHAUSTED_HINT)
    raise last_error
