import asyncio
import httpx
from gsuid_core.logger import logger

from ...SteamConfig import SteamConfig
from ..database.models_cache import SteamApiCache

# 内存快速缓存，避免同一进程生命周期内重复网络请求
_COVER_MEMORY_CACHE: dict[str, str] = {}
_OFFICIAL_FAILED_CACHE: set[str] = set()

# 官方标准 Fastly CDN 横板封面模版
OFFICIAL_HEADER_TEMPLATE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
OFFICIAL_CAPSULE_TEMPLATE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg"


def get_official_cover_url(appid: str | int, variant: str = "header") -> str:
    """获取官方标准封面直链（同步拼接）。
    
    variant:
      - 'header': 商店横幅封面 (460x215)
      - 'capsule_sm_120': 小胶囊图
    """
    aid = str(appid).strip()
    if variant == "capsule_sm_120":
        return OFFICIAL_CAPSULE_TEMPLATE.format(appid=aid)
    return OFFICIAL_HEADER_TEMPLATE.format(appid=aid)


def _get_http_client(timeout: float = 6.0) -> httpx.AsyncClient:
    """创建复用代理配置的 httpx.AsyncClient"""
    proxy = SteamConfig.get_config("HttpProxy").data
    if proxy and proxy.strip():
        return httpx.AsyncClient(timeout=timeout, proxy=proxy.strip())
    return httpx.AsyncClient(timeout=timeout)


async def check_official_cover_accessible(appid: str | int, timeout: float = 1.5) -> bool:
    """轻量异步检测官方封面是否可正常访问 (HTTP 200)。"""
    aid = str(appid).strip()
    url = get_official_cover_url(aid, "header")
    try:
        async with _get_http_client(timeout=timeout) as client:
            resp = await client.head(url)
            if resp.status_code == 200:
                return True
            if resp.status_code == 404:
                return False
            # 其他状态码尝试微量 GET 探测
            resp_get = await client.get(url, headers={"Range": "bytes=0-0"})
            return resp_get.status_code in (200, 206)
    except Exception:
        # 网络波动等情况不轻易判定为 404
        return False


def _sanitize_cover_url(url: str) -> str:
    """清洗与规范化封面 URL，将带防盗链限制的 Akamai / Cloudflare CDN 域名转为 Fastly CDN。"""
    if not url:
        return url
    if "shared.akamai.steamstatic.com" in url:
        url = url.replace("shared.akamai.steamstatic.com", "shared.fastly.steamstatic.com")
    elif "cdn.cloudflare.steamstatic.com" in url:
        url = url.replace("cdn.cloudflare.steamstatic.com", "shared.fastly.steamstatic.com")
    return url


async def fetch_griddb_cover(appid: str | int) -> str | None:
    """通过 SteamGridDB 获取社区封面图（静态最高票数，锁定官方横板尺寸 460x215,920x430）。"""
    allow_griddb = SteamConfig.get_config("AllowGridDBCover").data
    api_key = SteamConfig.get_config("GridDBApiKey").data
    if not allow_griddb or not api_key:
        return None

    aid = str(appid).strip()
    if not aid.isdigit():
        return None

    url = f"https://www.steamgriddb.com/api/v2/grids/steam/{aid}"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "SteamUID/1.0",
    }
    params = {
        "types": "static",  # 静态图
        "dimensions": "460x215,920x430",  # 严格锁定官方横板比例
        "nsfw": "false",  # 过滤成人内容
        "humor": "false",  # 过滤恶搞沙雕梗图
    }

    try:
        async with _get_http_client(timeout=5.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                json_data = resp.json()
                if json_data.get("success") and json_data.get("data"):
                    grids = json_data["data"]
                    if isinstance(grids, list) and len(grids) > 0:
                        # 默认第一项即为社区票数最高的图
                        top_grid = grids[0]
                        cover_url = top_grid.get("url") or top_grid.get("thumb")
                        if cover_url:
                            logger.info(f"[SteamUID] 成功通过 GridDB 获取到游戏封面 appid={aid}")
                            return cover_url
            elif resp.status_code == 404:
                logger.debug(f"[SteamUID] GridDB 未收录该游戏封面 appid={aid}")
            elif resp.status_code == 401:
                logger.warning("[SteamUID] Grid DB API Key 无效或未授权，请检查配置")
            else:
                logger.warning(f"[SteamUID] 请求 GridDB 异常 status={resp.status_code} appid={aid}")
    except Exception as e:
        logger.warning(f"[SteamUID] 请求 GridDB 网络错误 appid={aid}: {e}")

    return None


async def get_game_cover_url(
    appid: str | int,
    header_image: str | None = None,
    is_official_failed: bool = False,
    skip_griddb: bool = False,
) -> str:
    """统一获取 Steam 游戏封面 URL。
    
    逻辑：
      1. 若已有官方详情接口返回的 header_image，直接采纳并缓存；
      2. 若命中内存或数据库持久化缓存，直接返回；
      3. 若已知官方异常 (is_official_failed) 或检测到官方 404，且开启了 GridDB 备选，则从 GridDB 获取最高票静态封面；
      4. 若 GridDB 未开启或无结果，返回官方默认直链（由前端模板 onerror 处理失败路径）。
    """
    aid = str(appid).strip()
    if not aid:
        return ""

    # 1. 如果已由官方详情接口获取到了有效的 header_image
    if header_image and header_image.startswith("http"):
        sanitized = _sanitize_cover_url(header_image)
        _COVER_MEMORY_CACHE[aid] = sanitized
        return sanitized

    # 2. 内存缓存优先
    if aid in _COVER_MEMORY_CACHE:
        return _sanitize_cover_url(_COVER_MEMORY_CACHE[aid])

    # 3. 数据库持久缓存
    try:
        cached_url = await SteamApiCache.get_cache(f"cover_{aid}")
        if cached_url:
            sanitized = _sanitize_cover_url(cached_url)
            _COVER_MEMORY_CACHE[aid] = sanitized
            return sanitized
    except Exception:
        pass

    # 4. 判定官方是否异常/404
    official_failed = is_official_failed or (aid in _OFFICIAL_FAILED_CACHE)
    if not official_failed:
        # 轻量探测官方 CDN
        accessible = await check_official_cover_accessible(aid)
        if not accessible:
            official_failed = True
            _OFFICIAL_FAILED_CACHE.add(aid)

    # 5. 官方异常时，尝试 GridDB 备选
    if official_failed and not skip_griddb:
        griddb_cover = await fetch_griddb_cover(aid)
        if griddb_cover:
            _COVER_MEMORY_CACHE[aid] = griddb_cover
            try:
                await SteamApiCache.upsert_cache(f"cover_{aid}", griddb_cover)
            except Exception:
                pass
            return griddb_cover

    # 6. 官方正常或所有备选均无果，退回官方直链
    default_url = get_official_cover_url(aid, "header")
    if not official_failed:
        _COVER_MEMORY_CACHE[aid] = default_url
    return default_url


async def resolve_games_covers(
    games: list[dict],
    appid_key: str = "appid",
    cover_key: str = "cover_url",
    max_concurrency: int = 10,
) -> list[dict]:
    """批量并发解析多个游戏的封面 URL，常用于游戏墙、列表展示。"""
    sem = asyncio.Semaphore(max_concurrency)

    async def _resolve_one(game: dict):
        aid = game.get(appid_key)
        if not aid:
            return
        existing_cover = game.get(cover_key)
        async with sem:
            cover = await get_game_cover_url(aid, header_image=existing_cover)
            game[cover_key] = cover

    await asyncio.gather(*[_resolve_one(g) for g in games], return_exceptions=True)
    return games
