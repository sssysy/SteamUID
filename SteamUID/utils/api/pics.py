"""steamcmd.net PICS 公开元数据查询。

第三方 JSON 随用随请求，不落盘；字段提取由调用方处理。
"""

from dataclasses import dataclass
from collections.abc import Mapping

from .client import make_async_client, request_ok_response
from .models import PicsInfoResponse
from .endpoints import STEAMCMD_INFO_URL

_TAG = "构建信息"


@dataclass(frozen=True)
class AppBuildMeta:
    """app 的最新公开构建：公开分支 buildid 与 depot id -> 公开 manifest gid。"""

    buildid: str
    depot_manifests: dict[str, str]


def _as_map(value: object) -> Mapping[str, object]:
    """steamcmd 响应里子对象类型未知，在此边界处收窄为映射。"""
    if not isinstance(value, dict):
        raise ValueError("steamcmd 响应格式异常")
    return value


async def get_app_info(
    appid: str,
    *,
    proxy: str | None = None,
    timeout: float = 20.0,
) -> PicsInfoResponse:
    """取 app 的 PICS 元数据原始响应。"""
    aid = str(appid).strip()
    if not aid.isdigit():
        raise ValueError(f"无效的 appid: {aid}")

    url = STEAMCMD_INFO_URL.format(appid=aid)
    async with make_async_client(proxy=proxy, timeout=timeout) as client:
        resp = await request_ok_response(client, "GET", url, tag=_TAG, timeout=timeout)

    payload: PicsInfoResponse = resp.json()
    return payload


async def get_app_build_meta(
    appid: str,
    *,
    proxy: str | None = None,
    timeout: float = 20.0,
) -> AppBuildMeta:
    """从 PICS 元数据提取最新公开构建；共享 depot 不属于本 app，不参与伪造。"""
    aid = str(appid).strip()
    payload = await get_app_info(aid, proxy=proxy, timeout=timeout)

    if "data" not in payload or aid not in payload["data"]:
        raise ValueError(f"steamcmd 未返回 app {aid} 的数据")
    data: Mapping[str, object] = payload["data"]
    entry = _as_map(data[aid])

    if "depots" not in entry:
        raise ValueError(f"app {aid} 缺少 depots 字段")
    depots = _as_map(entry["depots"])

    if "branches" not in depots:
        raise ValueError(f"app {aid} 缺少公开分支信息")
    branches = _as_map(depots["branches"])
    if "public" not in branches:
        raise ValueError(f"app {aid} 缺少公开分支信息")
    public = _as_map(branches["public"])
    buildid = public["buildid"] if "buildid" in public else ""
    if not isinstance(buildid, str) or not buildid:
        raise ValueError(f"app {aid} 的公开分支缺少 buildid")

    manifests: dict[str, str] = {}
    for depot_id, depot_value in depots.items():
        if not depot_id.isdigit():
            continue
        depot = _as_map(depot_value)
        if "sharedinstall" in depot or "depotfromapp" in depot or "manifests" not in depot:
            continue
        depot_manifests = _as_map(depot["manifests"])
        if "public" not in depot_manifests:
            continue
        manifest = _as_map(depot_manifests["public"])
        gid = manifest["gid"] if "gid" in manifest else ""
        if isinstance(gid, str) and gid:
            manifests[depot_id] = gid

    return AppBuildMeta(buildid=buildid, depot_manifests=manifests)
