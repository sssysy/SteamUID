"""SteamID / 好友码互转，个人资料页解析与多格式身份输出。"""

import re
from typing import Literal
from dataclasses import dataclass

_BASE_STEAM_ID64 = 76561197960265728

# 只认 steamcommunity 个人资料页，尾部路径 / 查询 / 锚点一律截掉
_PROFILE_PAGE_RE = re.compile(
    r"^https?://(?:www\.)?steamcommunity\.com/(?P<kind>profiles|id)/(?P<value>[^/?#\s]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProfilePageRef:
    """个人资料页解析结果：profiles 直出 steamid64，id 是待换取的 vanity。"""

    kind: Literal["steamid64", "vanity"]
    value: str


def steamid64_to_friend_code(steamid64: str) -> str:
    """steamid64 转好友码（账号 ID）。"""
    return str(int(steamid64) - _BASE_STEAM_ID64)


def friend_code_to_steamid64(friend_code: str) -> str:
    """好友码（账号 ID）转 steamid64。"""
    return str(_BASE_STEAM_ID64 + int(friend_code))


def auto2steamid64(text: str) -> str | None:
    """把好友码或 steamid64 统一成 steamid64；空串或非数字返回 None。"""
    raw = text.strip()
    if not raw.isdigit():
        return None
    value = int(raw)
    if value >= _BASE_STEAM_ID64:
        return str(value)
    return str(_BASE_STEAM_ID64 + value)


def parse_profile_page(text: str) -> ProfilePageRef | None:
    """解析个人资料页 URL；profiles 段非数字或并非资料页时返回 None。"""
    match = _PROFILE_PAGE_RE.match(text.strip())
    if match is None:
        return None
    value = match.group("value")
    if match.group("kind").lower() == "profiles":
        return ProfilePageRef(kind="steamid64", value=value) if value.isdigit() else None
    return ProfilePageRef(kind="vanity", value=value)


def steamid64_to_legacy_id(steamid64: str) -> str:
    """steamid64 转旧式 STEAM_X:Y:Z；个人账号的 X 恒为 0。"""
    account_id = int(steamid64_to_friend_code(steamid64))
    return f"STEAM_0:{account_id & 1}:{account_id >> 1}"


def steamid64_to_steamid3(steamid64: str) -> str:
    """steamid64 转 steamID3（[U:1:账号 ID]）。"""
    return f"[U:1:{steamid64_to_friend_code(steamid64)}]"


def steamid64_to_hex_id(steamid64: str) -> str:
    """steamid64 的十六进制表示，小写且不带 0x 前缀。"""
    return format(int(steamid64), "x")


def steamid64_to_community_url(steamid64: str) -> str:
    """由 steamid64 拼官方原始社区 URL。"""
    return f"https://steamcommunity.com/profiles/{steamid64}"


def vanity_to_community_url(vanity: str) -> str:
    """由自定义域名拼官方个人资料页 URL。"""
    return f"https://steamcommunity.com/id/{vanity}"
