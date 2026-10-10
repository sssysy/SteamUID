"""Steam 各接口的响应结构声明。

只声明插件会读取的字段，Steam 多返回的字段在运行时忽略；标 total=False 的
结构表示字段可能缺失，调用方需自行做存在性判断。
"""

from typing import TypedDict


class RsaKeyPayload(TypedDict, total=False):
    publickey_mod: str
    publickey_exp: str
    timestamp: str


class RsaKeyResponse(TypedDict):
    response: RsaKeyPayload


class AllowedConfirmation(TypedDict, total=False):
    confirmation_type: int


class BeginAuthSessionPayload(TypedDict, total=False):
    client_id: str
    request_id: str
    steamid: str
    allowed_confirmations: list[AllowedConfirmation]


class BeginAuthSessionResponse(TypedDict):
    response: BeginAuthSessionPayload


class PollAuthStatusPayload(TypedDict, total=False):
    refresh_token: str
    access_token: str
    had_remote_interaction: bool


class PollAuthStatusResponse(TypedDict):
    response: PollAuthStatusPayload


class AccessTokenPayload(TypedDict, total=False):
    access_token: str


class AccessTokenResponse(TypedDict):
    response: AccessTokenPayload


class AuthLoginDone(TypedDict):
    """登录已完成，拿到 steamid64 与双 token。"""

    ok: bool
    done: bool
    need_2fa: bool
    steamid64: str


class AuthLoginPending(TypedDict):
    """等待两步验证。"""

    ok: bool
    done: bool
    need_2fa: bool
    can_app_confirm: bool
    hint: str


AuthStartResult = AuthLoginDone | AuthLoginPending


class AppConfirmDone(TypedDict):
    ok: bool
    done: bool
    steamid64: str


class AppConfirmWaiting(TypedDict):
    ok: bool
    done: bool
    msg: str


AppConfirmResult = AppConfirmDone | AppConfirmWaiting


class AuthCodeResult(TypedDict):
    ok: bool
    done: bool
    steamid64: str


class SteamCredentials(TypedDict):
    steamid64: str
    account_name: str
    access_token: str
    refresh_token: str
    session_id: str
    cookies: dict[str, str]


class PlayerSummary(TypedDict, total=False):
    steamid: str
    personaname: str
    profileurl: str
    avatar: str
    avatarmedium: str
    avatarfull: str
    avatarhash: str
    personastate: int
    communityvisibilitystate: int
    profilestate: int
    timecreated: int
    lastlogoff: int
    realname: str
    primaryclanid: str
    loccountrycode: str
    locstatecode: str
    loccityid: int
    gameid: str
    gameextrainfo: str
    gameserverip: str


class PlayerSummariesPayload(TypedDict, total=False):
    players: list[PlayerSummary]


class PlayerSummariesResponse(TypedDict, total=False):
    response: PlayerSummariesPayload


class OwnedGame(TypedDict, total=False):
    appid: int
    name: str
    playtime_forever: int
    playtime_2weeks: int
    playtime_windows_forever: int
    playtime_mac_forever: int
    playtime_linux_forever: int
    playtime_deck_forever: int
    rtime_last_played: int
    img_icon_url: str
    img_logo_url: str
    has_community_visible_stats: bool
    content_descriptorids: list[int]


class OwnedGamesPayload(TypedDict, total=False):
    game_count: int
    games: list[OwnedGame]


class OwnedGamesResponse(TypedDict):
    response: OwnedGamesPayload


class PlayerAchievement(TypedDict, total=False):
    apiname: str
    achieved: int
    unlocktime: int
    name: str
    description: str


class PlayerStatsPayload(TypedDict, total=False):
    steamID: str
    gameName: str
    achievements: list[PlayerAchievement]
    success: bool
    error: str


class PlayerAchievementsResponse(TypedDict):
    playerstats: PlayerStatsPayload


class AchievementSchemaEntry(TypedDict, total=False):
    name: str
    defaultvalue: int
    displayName: str
    hidden: int
    description: str
    icon: str
    icongray: str


class AvailableGameStats(TypedDict, total=False):
    achievements: list[AchievementSchemaEntry]


class SchemaGamePayload(TypedDict, total=False):
    gameName: str
    gameVersion: str
    availableGameStats: AvailableGameStats


class SchemaForGameResponse(TypedDict, total=False):
    game: SchemaGamePayload


class ReleaseDate(TypedDict, total=False):
    coming_soon: bool
    date: str


class Platforms(TypedDict, total=False):
    windows: bool
    mac: bool
    linux: bool


class Genre(TypedDict, total=False):
    id: str
    description: str


class Category(TypedDict, total=False):
    id: int
    description: str


class Screenshot(TypedDict, total=False):
    id: int
    path_thumbnail: str
    path_full: str


MovieSource = TypedDict("MovieSource", {"max": str, "480": str, "720": str}, total=False)


class Movie(TypedDict, total=False):
    id: int
    name: str
    thumbnail: str
    webm: MovieSource
    mp4: MovieSource
    highlight: bool


class PriceOverview(TypedDict, total=False):
    currency: str
    initial: int
    final: int
    discount_percent: int
    initial_formatted: str
    final_formatted: str


class Recommendations(TypedDict, total=False):
    total: int


class Metacritic(TypedDict, total=False):
    score: int
    url: str


class SupportInfo(TypedDict, total=False):
    url: str
    email: str


class ContentDescriptors(TypedDict, total=False):
    ids: list[int]
    notes: str


class Requirements(TypedDict, total=False):
    minimum: str
    recommended: str


class PackageGroupSub(TypedDict, total=False):
    text: str
    description: str
    price_in_cents_with_discount: int


class PackageGroup(TypedDict, total=False):
    name: str
    title: str
    description: str
    selection_text: str
    save_text: str
    display_type: int
    is_recurring_subscription: str
    subs: list[PackageGroupSub]


class HighlightedAchievement(TypedDict, total=False):
    name: str
    path: str


class AchievementsInfo(TypedDict, total=False):
    total: int
    highlighted: list[HighlightedAchievement]


class AppDetailsData(TypedDict, total=False):
    type: str
    name: str
    steam_appid: int
    required_age: int
    is_free: bool
    controller_support: str
    dlc: list[int]
    detailed_description: str
    about_the_game: str
    short_description: str
    supported_languages: str
    header_image: str
    capsule_image: str
    capsule_imagev5: str
    website: str
    pc_requirements: Requirements
    mac_requirements: Requirements
    linux_requirements: Requirements
    developers: list[str]
    publishers: list[str]
    price_overview: PriceOverview
    packages: list[int]
    package_groups: list[PackageGroup]
    platforms: Platforms
    metacritic: Metacritic
    categories: list[Category]
    genres: list[Genre]
    screenshots: list[Screenshot]
    movies: list[Movie]
    recommendations: Recommendations
    achievements: AchievementsInfo
    release_date: ReleaseDate
    support_info: SupportInfo
    background: str
    background_raw: str
    content_descriptors: ContentDescriptors


class AppDetailsEntry(TypedDict, total=False):
    success: bool
    data: AppDetailsData


class ProfileItemEntry(TypedDict, total=False):
    communityitemid: str
    item_type: int
    item_title: str
    item_description: str
    image_small: str
    image_large: str


class ProfileItemsEquippedPayload(TypedDict, total=False):
    avatar_frame: ProfileItemEntry
    animated_avatar: ProfileItemEntry
    profile_background: ProfileItemEntry
    mini_profile_background: ProfileItemEntry


class ProfileItemsEquippedResponse(TypedDict, total=False):
    response: ProfileItemsEquippedPayload


MiniprofileBackground = TypedDict(
    "MiniprofileBackground",
    {"image": str, "video/webm": str, "video/mp4": str},
    total=False,
)


class MiniprofileFavoriteBadge(TypedDict, total=False):
    icon: str
    name: str
    xp: int


class MiniprofilePayload(TypedDict, total=False):
    level: int
    level_class: str
    avatar_url: str
    avatar_frame: str
    profile_background: MiniprofileBackground
    favorite_badge: MiniprofileFavoriteBadge


class StoreSearchPrice(TypedDict, total=False):
    currency: str
    initial: int
    final: int
    discount_percent: int


class StoreSearchItem(TypedDict, total=False):
    type: str
    id: int
    name: str
    tiny_image: str
    metascore: str
    price: StoreSearchPrice
    platforms: Platforms
    controller_support: str
    streamingvideo: bool


class StoreSearchResponse(TypedDict, total=False):
    total: int
    items: list[StoreSearchItem]


class StoreEventAnnouncementBody(TypedDict, total=False):
    gid: str
    clanid: str
    posterid: str
    headline: str
    body: str
    posttime: int
    updatetime: int


class StoreEvent(TypedDict, total=False):
    gid: str
    clanid: str
    event_name: str
    event_type: int
    rtime32_start_time: int
    rtime32_post_time: int
    rtime32_end_time: int
    jsondata: str
    announcement_body: StoreEventAnnouncementBody
    clan_image: str
    appid: int


class PartnerEventsResponse(TypedDict, total=False):
    events: list[StoreEvent]
    num_events: int


class WishlistItem(TypedDict, total=False):
    appid: int
    priority: int
    date_added: int


class WishlistPayload(TypedDict, total=False):
    items: list[WishlistItem]


class WishlistResponse(TypedDict, total=False):
    response: WishlistPayload


class WishlistMutationResponse(TypedDict, total=False):
    response: dict[str, bool]


class YearReviewImage(TypedDict, total=False):
    url_path: str
    height: int
    width: int


class YearReviewPayload(TypedDict, total=False):
    images: list[YearReviewImage]
    status: int


class YearReviewResponse(TypedDict):
    response: YearReviewPayload


class ServerInfoPayload(TypedDict, total=False):
    servertime: int
    servertimestring: str


class ServerInfoResponse(TypedDict):
    response: ServerInfoPayload


class PurchaseReceiptLineItem(TypedDict, total=False):
    line_item_description: str
    line_item_type: int
    transactionid: str


class PurchaseReceiptInfo(TypedDict, total=False):
    line_items: list[PurchaseReceiptLineItem]


class RegisterCdKeyResponse(TypedDict, total=False):
    success: int
    purchase_result_details: int
    purchase_receipt_info: PurchaseReceiptInfo


class DiscoveryQueueResponse(TypedDict, total=False):
    queue: list[int]


class GridDbAuthor(TypedDict, total=False):
    name: str
    steam64: str
    avatar: str


class GridDbGrid(TypedDict, total=False):
    id: int
    score: int
    style: str
    width: int
    height: int
    nsfw: bool
    humor: bool
    language: str
    url: str
    thumb: str
    tags: list[str]
    author: GridDbAuthor


class GridDbGridsResponse(TypedDict, total=False):
    success: bool
    page: int
    total: int
    limit: int
    data: list[GridDbGrid]


class GridDbBatchEntry(TypedDict, total=False):
    id: int
    success: bool
    status: int
    data: list[GridDbGrid]


class GridDbBatchResponse(TypedDict, total=False):
    success: bool
    data: list[GridDbBatchEntry]


class PicsManifest(TypedDict, total=False):
    gid: str
    size: str
    download: str


class PicsBranch(TypedDict, total=False):
    buildid: str
    timeupdated: str
    description: str
    pwdrequired: str


class PicsDepot(TypedDict, total=False):
    manifests: dict[str, PicsManifest]
    sharedinstall: str
    depotfromapp: str
    dlcappid: str
    maxsize: str
    config: dict[str, str]
    branches: dict[str, PicsBranch]
    baselanguages: list[str]


class PicsCommon(TypedDict, total=False):
    name: str
    type: str
    oslist: str
    gameid: str


class PicsConfig(TypedDict, total=False):
    installdir: str
    launch: dict[str, str]


class PicsAppEntry(TypedDict, total=False):
    appid: str
    common: PicsCommon
    config: PicsConfig
    depots: dict[str, PicsDepot]


class PicsInfoResponse(TypedDict, total=False):
    status: str
    data: dict[str, PicsAppEntry]
