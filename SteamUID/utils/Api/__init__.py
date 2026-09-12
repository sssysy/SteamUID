# -*- coding: utf-8 -*-
"""Steam 协议层：指令包只调用此处函数，不直接拼 URL / new httpx。"""

from .account import (
    get_account_session,
    get_proxy_dict,
    get_proxy_url,
    get_valid_access_token,
    get_valid_session,
    is_private_data_allowed,
    refresh_account_tokens,
)
from .auth import (
    AuthCodeInvalid,
    LoginIncorrect,
    SteamAuthError,
    SteamWebAuth,
    TwoFactorAuthRequired,
    generate_session_id,
    rsa_encrypt_password,
)
from .client import (
    DEFAULT_USER_AGENT,
    STEAM_DOMAINS,
    make_async_client,
)
from .public import (
    clear_user_mem_cache,
    get_archivement_img,
    get_archivement_info,
    get_archivement_schema,
    get_game_announcements,
    get_game_icon_url,
    get_game_info,
    get_miniprofile,
    get_price_data,
    get_profile_items_equipped,
    get_steamlibrary_by_steamid64,
    get_user_Summaries,
    get_user_wishlist,
    search_game_store,
)
from .store import (
    SteamStoreAuthExpiredError,
    clear_discovery_queue_app,
    generate_discovery_queue,
    register_cdkey,
)
from .cover import (
    fetch_griddb_cover,
    get_game_cover_url,
    get_official_cover_url,
    resolve_games_covers,
)
from .wishlist import add_to_wishlist, remove_from_wishlist

__all__ = [
    # auth
    "SteamWebAuth",
    "SteamAuthError",
    "LoginIncorrect",
    "TwoFactorAuthRequired",
    "AuthCodeInvalid",
    "rsa_encrypt_password",
    "generate_session_id",
    # account
    "get_proxy_url",
    "get_proxy_dict",
    "get_account_session",
    "refresh_account_tokens",
    "get_valid_session",
    "get_valid_access_token",
    "is_private_data_allowed",
    # client
    "make_async_client",
    "DEFAULT_USER_AGENT",
    "STEAM_DOMAINS",
    # public
    "get_user_Summaries",
    "get_game_info",
    "get_game_icon_url",
    "get_steamlibrary_by_steamid64",
    "get_archivement_info",
    "get_archivement_img",
    "get_archivement_schema",
    "get_price_data",
    "get_profile_items_equipped",
    "get_miniprofile",
    "search_game_store",
    "get_game_announcements",
    "get_user_wishlist",
    "clear_user_mem_cache",
    # cover
    "get_game_cover_url",
    "get_official_cover_url",
    "fetch_griddb_cover",
    "resolve_games_covers",
    # wishlist
    "add_to_wishlist",
    "remove_from_wishlist",
    # store
    "register_cdkey",
    "generate_discovery_queue",
    "clear_discovery_queue_app",
    "SteamStoreAuthExpiredError",
]
