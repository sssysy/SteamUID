import httpx
from gsuid_core.logger import logger

from ...SteamConfig import SteamConfig
from ..database.models_cache import SteamApiCache
from .client import make_async_client

# 官方标准 Fastly CDN 横板封面模版
OFFICIAL_HEADER_TEMPLATE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
OFFICIAL_CAPSULE_TEMPLATE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg"

# GridDB 批量查询单次携带的最大游戏数（逗号分隔多 id）
GRIDDB_BATCH_SIZE = 50


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
    """创建复用统一代理/UA 配置的 httpx.AsyncClient"""
    return make_async_client(timeout=timeout)


def _griddb_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "SteamUID/1.0",
    }


def _griddb_params() -> dict:
    return {
        "types": "static",  # 静态图
        "dimensions": "460x215,920x430",  # 严格锁定官方横板比例
        "nsfw": "false",  # 过滤成人内容
        "humor": "false",  # 过滤恶搞沙雕梗图
    }


def _pick_grid(grids: list) -> str | None:
    """取最高票横板图（接口默认按票数排序，第一张即最高票）。"""
    for grid in grids or []:
        cover = grid.get("url") or grid.get("thumb")
        if cover:
            return cover
    return None


async def fetch_griddb_cover(appid: str | int) -> str | None:
    """通过 SteamGridDB 获取单个游戏的社区封面（静态最高票，锁定官方横板尺寸）。"""
    allow_griddb = SteamConfig.get_config("AllowGridDBCover").data
    api_key = SteamConfig.get_config("GridDBApiKey").data
    if not allow_griddb or not api_key:
        return None

    aid = str(appid).strip()
    if not aid.isdigit():
        return None

    url = f"https://www.steamgriddb.com/api/v2/grids/steam/{aid}"

    try:
        async with _get_http_client(timeout=5.0) as client:
            resp = await client.get(url, headers=_griddb_headers(api_key), params=_griddb_params())
            if resp.status_code == 200:
                json_data = resp.json()
                if json_data.get("success") and json_data.get("data"):
                    cover = _pick_grid(json_data["data"])
                    if cover:
                        logger.info(f"[SteamUID] 成功通过 GridDB 获取到游戏封面 appid={aid}")
                        return cover
            elif resp.status_code == 404:
                logger.debug(f"[SteamUID] GridDB 未收录该游戏封面 appid={aid}")
            elif resp.status_code == 401:
                logger.warning("[SteamUID] Grid DB API Key 无效或未授权，请检查配置")
            else:
                logger.warning(f"[SteamUID] 请求 GridDB 异常 status={resp.status_code} appid={aid}")
    except Exception as e:
        logger.warning(f"[SteamUID] 请求 GridDB 网络错误 appid={aid}: {e}")

    return None


async def fetch_griddb_covers_batch(appids: list[str]) -> dict[str, str]:
    """批量通过 SteamGridDB 获取社区封面。
    Returns:
        ``{appid: cover_url}``，只包含成功获取的游戏。"""
    allow_griddb = SteamConfig.get_config("AllowGridDBCover").data
    api_key = SteamConfig.get_config("GridDBApiKey").data
    if not allow_griddb or not api_key or not appids:
        return {}

    valid = [str(a).strip() for a in appids if str(a).strip().isdigit()]
    if not valid:
        return {}

    url = f"https://www.steamgriddb.com/api/v2/grids/steam/{','.join(valid)}"
    result: dict[str, str] = {}
    try:
        async with _get_http_client(timeout=8.0) as client:
            resp = await client.get(
                url, headers=_griddb_headers(api_key), params=_griddb_params()
            )
            if resp.status_code not in (200, 207):
                logger.warning(
                    f"[SteamUID] GridDB 批量查询异常 status={resp.status_code} 数量={len(valid)}"
                )
                return {}
            items = resp.json().get("data") or []
    except Exception as e:
        logger.warning(f"[SteamUID] GridDB 批量查询网络错误: {e}")
        return {}

    if len(items) != len(valid):
        logger.warning(
            f"[SteamUID] GridDB 批量返回数量与请求不一致 请求={len(valid)} 返回={len(items)}"
        )
    for aid, item in zip(valid, items):
        if not isinstance(item, dict) or item.get("status") != 200:
            continue
        cover = _pick_grid(item.get("data"))
        if cover:
            result[aid] = cover
    return result


async def get_game_cover_url(
    appid: str | int,
    header_image: str | None = None,
    skip_griddb: bool = False,
) -> str:
    """统一获取 Steam 游戏封面 URL。"""
    aid = str(appid).strip()
    if not aid:
        return ""

    # 1. 详情接口已给出有效 header_image
    if header_image and header_image.startswith("http"):
        try:
            await SteamApiCache.upsert_cache(f"cover_{aid}", header_image)
        except Exception:
            pass
        return header_image

    # 2. DB 持久缓存
    try:
        cached_url = await SteamApiCache.get_cache(f"cover_{aid}")
        if cached_url:
            return cached_url
    except Exception:
        pass

    # 3. GridDB 社区封面
    if not skip_griddb:
        griddb_cover = await fetch_griddb_cover(aid)
        if griddb_cover:
            try:
                await SteamApiCache.upsert_cache(f"cover_{aid}", griddb_cover)
            except Exception:
                pass
            return griddb_cover

    # 4. 官方直链兜底（404 时由模板 onerror 显示默认占位图）
    return get_official_cover_url(aid, "header")


async def resolve_games_covers(
    games: list[dict],
    appid_key: str = "appid",
    cover_key: str = "cover_url",
) -> list[dict]:
    """批量解析多个游戏的封面（游戏墙、列表展示）。"""
    missing: list[str] = []
    for game in games:
        aid = str(game.get(appid_key) or "").strip()
        if not aid or game.get(cover_key):
            continue
        try:
            cached = await SteamApiCache.get_cache(f"cover_{aid}")
        except Exception:
            cached = None
        if cached:
            game[cover_key] = cached
        else:
            missing.append(aid)

    for i in range(0, len(missing), GRIDDB_BATCH_SIZE):
        batch = missing[i : i + GRIDDB_BATCH_SIZE]
        found = await fetch_griddb_covers_batch(batch)
        if not found:
            continue
        for aid, cover in found.items():
            try:
                await SteamApiCache.upsert_cache(f"cover_{aid}", cover)
            except Exception:
                pass
        for game in games:
            aid = str(game.get(appid_key) or "").strip()
            if aid in found:
                game[cover_key] = found[aid]

    for game in games:
        if not game.get(cover_key):
            aid = str(game.get(appid_key) or "").strip()
            if aid:
                game[cover_key] = get_official_cover_url(aid, "header")

    return games
