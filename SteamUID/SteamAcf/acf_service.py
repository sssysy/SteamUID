from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from gsuid_core.bot import Bot
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.Api import get_app_build_meta
from ..utils.exceptions import SteamValidationError
from ..utils.helpers.acf_vdf import (
    apply_latest_manifest,
    dumps_acf,
    get_app_state,
    parse_acf,
)

CACHE_DIR: Path = get_res_path("SteamUID") / "cache"


def _safe_name(file_name: str) -> str:
    name = Path(file_name or "appmanifest.acf").name
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name) or "appmanifest.acf"


async def _load_file_bytes(ev: Event) -> tuple[bytes, str]:
    if not ev.file:
        raise SteamValidationError("请在同一条消息中附上 appmanifest_xxx.acf 文件")
    file_name = _safe_name(ev.file_name or "appmanifest.acf")
    if not file_name.lower().endswith(".acf"):
        raise SteamValidationError("仅支持 .acf 文件")

    raw = str(ev.file)
    if ev.file_type == "url" or raw.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(raw)
            if resp.status_code != 200:
                raise SteamValidationError(f"下载 acf 文件失败: HTTP {resp.status_code}")
            content = resp.content
    else:
        try:
            content = base64.b64decode(raw)
        except Exception as e:
            raise SteamValidationError("acf 文件内容解析失败") from e

    if not content:
        raise SteamValidationError("acf 文件内容为空")
    return content, file_name


def _resolve_game_name(state: dict[str, Any], meta: dict[str, Any]) -> str:
    name = str(state.get("name") or "").strip()
    if name:
        return name
    name = str(meta.get("name") or "").strip()
    return name or str(state.get("appid") or meta.get("appid") or "")


async def process_acf_update(bot: Bot, ev: Event) -> None:
    content, file_name = await _load_file_bytes(ev)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    tmp_in = CACHE_DIR / f"{token}_{file_name}"
    tmp_out = CACHE_DIR / f"{token}_updated_{file_name}"

    try:
        tmp_in.write_bytes(content)
        root = parse_acf(content.decode("utf-8", errors="replace"))
        state = get_app_state(root)
        appid = str(state.get("appid") or "").strip()
        if not appid.isdigit():
            raise SteamValidationError("ACF 中缺少有效的 appid")

        meta = await get_app_build_meta(appid)
        updated_depots = apply_latest_manifest(
            root,
            buildid=meta["buildid"],
            depot_manifests=meta["depot_manifests"],
        )
        game_name = _resolve_game_name(state, meta)

        new_text = dumps_acf(root)
        tmp_out.write_text(new_text, encoding="utf-8", newline="\n")
        out_bytes = tmp_out.read_bytes()

        logger.info(
            f"[SteamAcf] appid={appid} buildid={meta['buildid']} depots={updated_depots}"
        )
        await bot.send(MessageSegment.file(out_bytes, file_name))
        await bot.send(f"已将游戏 {game_name} 的 manifest 文件伪造为最新版本！")
    finally:
        for path in (tmp_in, tmp_out):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                logger.warning(f"[SteamAcf] 清理临时文件失败: {path}")
