# -*- coding: utf-8 -*-
"""Steam 接口路径常量集中地。"""

from ...SteamConfig.interface import SteamAPI

API_BASE_DEFAULT = "https://api.steampowered.com"
STORE_BASE_DEFAULT = "https://store.steampowered.com"
COMMUNITY_BASE_DEFAULT = "https://steamcommunity.com"

# IAuthenticationService
AUTH_GET_RSA_KEY = "/IAuthenticationService/GetPasswordRSAPublicKey/v1"
AUTH_BEGIN_CREDENTIALS = "/IAuthenticationService/BeginAuthSessionViaCredentials/v1"
AUTH_POLL_STATUS = "/IAuthenticationService/PollAuthSessionStatus/v1"
AUTH_UPDATE_GUARD_CODE = "/IAuthenticationService/UpdateAuthSessionWithSteamGuardCode/v1"
AUTH_GENERATE_ACCESS_TOKEN = "/IAuthenticationService/GenerateAccessTokenForApp/v1"

# IWishlistService（需 access_token）
WISHLIST_ADD = "/IWishlistService/AddToWishlist/v1"
WISHLIST_REMOVE = "/IWishlistService/RemoveFromWishlist/v1"

# Store 页面（需 cookie session）
STORE_REGISTER_KEY = "/account/ajaxregisterkey/"
STORE_GENERATE_DISCOVERY_QUEUE = "/explore/generatenewdiscoveryqueue"
STORE_ACCOUNT_HOME = "/account/"

# IFamilyGroupsService（预留：需 access_token）
FAMILY_GET_FOR_USER = "/IFamilyGroupsService/GetFamilyGroupForUser/v1"
FAMILY_GET_SHARED_APPS = "/IFamilyGroupsService/GetSharedLibraryApps/v1"

__all__ = [
    "SteamAPI",
    "API_BASE_DEFAULT",
    "STORE_BASE_DEFAULT",
    "COMMUNITY_BASE_DEFAULT",
    "AUTH_GET_RSA_KEY",
    "AUTH_BEGIN_CREDENTIALS",
    "AUTH_POLL_STATUS",
    "AUTH_UPDATE_GUARD_CODE",
    "AUTH_GENERATE_ACCESS_TOKEN",
    "WISHLIST_ADD",
    "WISHLIST_REMOVE",
    "STORE_REGISTER_KEY",
    "STORE_GENERATE_DISCOVERY_QUEUE",
    "STORE_ACCOUNT_HOME",
    "FAMILY_GET_FOR_USER",
    "FAMILY_GET_SHARED_APPS",
]
