"""Steam 接口路径常量与默认基址，不含任何请求逻辑。"""

API_BASE_DEFAULT = "https://api.steampowered.com"
STORE_BASE_DEFAULT = "https://store.steampowered.com"
COMMUNITY_BASE_DEFAULT = "https://steamcommunity.com"
COMMUNITY_CDN_BASE_DEFAULT = "https://community.fastly.steamstatic.com"
HELP_BASE_DEFAULT = "https://help.steampowered.com"
MEDIA_BASE_DEFAULT = "https://media.steampowered.com"
SHARED_CDN_BASE_DEFAULT = "https://shared.fastly.steamstatic.com"
STEAMCMD_INFO_URL = "https://api.steamcmd.net/v1/info/{appid}"
GRIDDB_API_BASE = "https://www.steamgriddb.com/api/v2"
AUGMENTED_STORE_LOW_URL = "https://api.augmentedsteam.com/prices/v2"

# IAuthenticationService / IWishlistService
AUTH_BEGIN_QR = "/IAuthenticationService/BeginAuthSessionViaQR/v1"
AUTH_POLL_STATUS = "/IAuthenticationService/PollAuthSessionStatus/v1"
AUTH_GENERATE_ACCESS_TOKEN = "/IAuthenticationService/GenerateAccessTokenForApp/v1"
WISHLIST_ADD = "/IWishlistService/AddToWishlist/v1"
WISHLIST_REMOVE = "/IWishlistService/RemoveFromWishlist/v1"

# IFamilyGroupsService
FAMILY_GET_GROUP_FOR_USER = "/IFamilyGroupsService/GetFamilyGroupForUser/v1"
FAMILY_GET_SHARED_LIBRARY_APPS = "/IFamilyGroupsService/GetSharedLibraryApps/v1"

# ISteamUser / IPlayerService / ISteamUserStats
API_GET_PLAYER_SUMMARIES = "/ISteamUser/GetPlayerSummaries/v2/"
API_GET_PLAYER_BANS = "/ISteamUser/GetPlayerBans/v1/"
API_GET_FRIEND_LIST = "/ISteamUser/GetFriendList/v1/"
API_RESOLVE_VANITY_URL = "/ISteamUser/ResolveVanityURL/v1/"
API_GET_OWNED_GAMES = "/IPlayerService/GetOwnedGames/v1/"
API_GET_RECENTLY_PLAYED_GAMES = "/IPlayerService/GetRecentlyPlayedGames/v1/"
API_GET_PLAYER_ACHIEVEMENTS = "/ISteamUserStats/GetPlayerAchievements/v1/"
API_GET_SCHEMA_FOR_GAME = "/ISteamUserStats/GetSchemaForGame/v2/"
API_GET_GLOBAL_ACHIEVEMENT_PERCENTAGES = "/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
API_GET_NUMBER_OF_CURRENT_PLAYERS = "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
API_GET_PROFILE_ITEMS_EQUIPPED = "/IPlayerService/GetProfileItemsEquipped/v1/"
API_GET_WISHLIST = "/IWishlistService/GetWishlist/v1/"
API_GET_USER_YEAR_IN_REVIEW_SHARE_IMAGE = "/ISaleFeatureService/GetUserYearInReviewShareImage/v1"
API_GET_SERVER_INFO = "/ISteamWebAPIUtil/GetServerInfo/v1"

# IStoreBrowseService，批量条目详情只接受 GET + input_json
API_STORE_BROWSE_GET_ITEMS = "/IStoreBrowseService/GetItems/v1/"

# IStoreTopSellersService / ISteamChartsService，只接受 GET + input_json
API_GET_WEEKLY_TOP_SELLERS = "/IStoreTopSellersService/GetWeeklyTopSellers/v1/"
API_GET_GAMES_BY_CONCURRENT_PLAYERS = "/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
API_GET_MOST_PLAYED_GAMES = "/ISteamChartsService/GetMostPlayedGames/v1/"

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
# 社区等级徽章精灵图（10 帧纵排，每帧 32px）
COMMUNITY_LEVEL_SPRITE = "/public/shared/images/community/{name}"

# 社区装扮素材（动画头像 / 迷你资料背景等）相对路径直链模板
COMMUNITY_ASSETS_TEMPLATE = SHARED_CDN_BASE_DEFAULT + "/community_assets/images/{path}"

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
