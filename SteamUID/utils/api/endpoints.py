"""Steam 接口路径常量与默认基址，不含任何请求逻辑。"""

API_BASE_DEFAULT = "https://api.steampowered.com"
STORE_BASE_DEFAULT = "https://store.steampowered.com"
COMMUNITY_BASE_DEFAULT = "https://steamcommunity.com"
HELP_BASE_DEFAULT = "https://help.steampowered.com"
MEDIA_BASE_DEFAULT = "https://media.steampowered.com"
SHARED_CDN_BASE_DEFAULT = "https://shared.fastly.steamstatic.com"
STEAMCMD_INFO_URL = "https://api.steamcmd.net/v1/info/{appid}"
GRIDDB_API_BASE = "https://www.steamgriddb.com/api/v2"

# IAuthenticationService / IWishlistService
AUTH_GET_RSA_KEY = "/IAuthenticationService/GetPasswordRSAPublicKey/v1"
AUTH_BEGIN_CREDENTIALS = "/IAuthenticationService/BeginAuthSessionViaCredentials/v1"
AUTH_POLL_STATUS = "/IAuthenticationService/PollAuthSessionStatus/v1"
AUTH_UPDATE_GUARD_CODE = "/IAuthenticationService/UpdateAuthSessionWithSteamGuardCode/v1"
AUTH_GENERATE_ACCESS_TOKEN = "/IAuthenticationService/GenerateAccessTokenForApp/v1"
WISHLIST_ADD = "/IWishlistService/AddToWishlist/v1"
WISHLIST_REMOVE = "/IWishlistService/RemoveFromWishlist/v1"

# ISteamUser / IPlayerService / ISteamUserStats
API_GET_PLAYER_SUMMARIES = "/ISteamUser/GetPlayerSummaries/v2/"
API_GET_OWNED_GAMES = "/IPlayerService/GetOwnedGames/v1/"
API_GET_PLAYER_ACHIEVEMENTS = "/ISteamUserStats/GetPlayerAchievements/v1/"
API_GET_SCHEMA_FOR_GAME = "/ISteamUserStats/GetSchemaForGame/v2/"
API_GET_PROFILE_ITEMS_EQUIPPED = "/IPlayerService/GetProfileItemsEquipped/v1/"
API_GET_WISHLIST = "/IWishlistService/GetWishlist/v1/"
API_GET_USER_YEAR_IN_REVIEW_SHARE_IMAGE = "/ISaleFeatureService/GetUserYearInReviewShareImage/v1"
API_GET_SERVER_INFO = "/ISteamWebAPIUtil/GetServerInfo/v1"

# 商店页面
STORE_GET_GAME_DETAILS = "/api/appdetails"
STORE_SEARCH = "/api/storesearch/"
STORE_EVENTS_PARTNER_PAGEABLE = "/events/ajaxgetpartnereventspageable/"
STORE_REGISTER_KEY = "/account/ajaxregisterkey/"
STORE_GENERATE_DISCOVERY_QUEUE = "/explore/generatenewdiscoveryqueue"
STORE_ACCOUNT_HOME = "/account/"
STORE_APP_PAGE = "/app/{appid}"
STORE_NEWS_VIEW = "/news/app/{appid}/view/{gid}"

# 社区页面
COMMUNITY_MINIPROFILE = "/miniprofile/{steamid32}/json"
COMMUNITY_PROFILE_XML = "/profiles/{steamid64}/?xml=1"

# 官方封面 / 图标直链模板
COVER_VARIANT_PATHS: dict[str, str] = {
    "header": "header.jpg",
    "library_600x900": "library_600x900.jpg",
    "library_hero": "library_hero.jpg",
    "capsule_616x353": "capsule_616x353.jpg",
    "capsule_467x181": "capsule_467x181.jpg",
    "capsule_231x87": "capsule_231x87.jpg",
    "capsule_184x69": "capsule_184x69.jpg",
    "capsule_sm_120": "capsule_sm_120.jpg",
}
COVER_ASSET_TEMPLATE = SHARED_CDN_BASE_DEFAULT + "/store_item_assets/steam/apps/{appid}/{variant}"
APP_ICON_TEMPLATE = MEDIA_BASE_DEFAULT + "/steamcommunity/public/images/apps/{appid}/{icon_hash}.jpg"
