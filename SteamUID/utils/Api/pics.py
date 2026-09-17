"""PICS 公开元数据：按 appid 获取最新 public buildid 与 depot manifest"""

from __future__ import annotations

from typing import Any

from ..exceptions import SteamAPIError
from .client import make_async_client

PICS_INFO_URL = "https://api.steamcmd.net/v1/info/{appid}"


async def get_app_build_meta(appid: str) -> dict[str, Any]:
    """返回 {appid, name, buildid, depot_manifests}；depot_manifests 仅含带 public manifest 的本 app depot"""
    appid = str(appid).strip()
    if not appid.isdigit():
        raise SteamAPIError(f"无效的 appid: {appid}")

    url = PICS_INFO_URL.format(appid=appid)
    async with make_async_client(timeout=20.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise SteamAPIError(f"获取 app {appid} 最新构建信息失败: HTTP {resp.status_code}")
        body = resp.json()

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise SteamAPIError(f"获取 app {appid} 最新构建信息失败: 响应格式异常")

    entry = data.get(appid)
    if not isinstance(entry, dict):
        raise SteamAPIError(f"获取 app {appid} 最新构建信息失败: 未找到该应用")

    common = entry.get("common") if isinstance(entry.get("common"), dict) else {}
    config = entry.get("config") if isinstance(entry.get("config"), dict) else {}
    depots = entry.get("depots") if isinstance(entry.get("depots"), dict) else {}
    branches = depots.get("branches") if isinstance(depots.get("branches"), dict) else {}
    public_branch = branches.get("public") if isinstance(branches.get("public"), dict) else {}

    buildid = public_branch.get("buildid")
    if not buildid:
        raise SteamAPIError(f"获取 app {appid} 最新构建信息失败: 无公开分支 buildid")

    depot_manifests: dict[str, str] = {}
    for depot_id, depot in depots.items():
        if depot_id in ("branches", "baselanguages", "hasdepotsindlc", "privatebranches"):
            continue
        if not isinstance(depot, dict):
            continue
        if depot.get("sharedinstall") or depot.get("depotfromapp"):
            continue
        manifests = depot.get("manifests") if isinstance(depot.get("manifests"), dict) else {}
        public = manifests.get("public") if isinstance(manifests.get("public"), dict) else {}
        gid = public.get("gid")
        if gid:
            depot_manifests[str(depot_id)] = str(gid)

    name = ""
    if isinstance(common, dict):
        name = str(common.get("name") or "")
    if not name and isinstance(config, dict):
        name = str(config.get("installdir") or "")

    return {
        "appid": appid,
        "name": name,
        "buildid": str(buildid),
        "depot_manifests": depot_manifests,
    }
