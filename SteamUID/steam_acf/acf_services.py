"""steam更新acf 实现：解析上传的 appmanifest，伪造为最新构建后回传文件。"""

import re
import uuid
import base64
import binascii
from pathlib import Path

import httpx

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from ..utils.api.pics import get_app_build_meta
from ..utils.downloader import CACHE_DIR, download
from ..utils.helper.acf import read_app_state, apply_latest_build

_TAG = "[Steam·更新ACF]"
_SUFFIX = ".acf"
_DEFAULT_NAME = "appmanifest.acf"
_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


async def process_acf_update(bot: Bot, ev: Event) -> None:
    """把上传 appmanifest 的 buildid 与各 depot manifest 伪造为最新后回传。"""
    text, file_name = await _read_upload(ev)
    state = read_app_state(text)
    if not state.appid.isdigit():
        raise ValueError("ACF 中缺少有效的 appid")

    try:
        meta = await get_app_build_meta(state.appid)
    except httpx.HTTPError as error:
        logger.warning(f"{_TAG} 查询公开构建失败 appid={state.appid}: {type(error).__name__}")
        raise ValueError(f"查询 app {state.appid} 的公开构建信息失败，请稍后重试") from error

    new_text, matched = apply_latest_build(text, buildid=meta.buildid, depot_manifests=meta.depot_manifests)
    if not matched:
        raise ValueError(f"app {state.appid} 的公开 depot 与 ACF 中已安装的 depot 没有交集，无法伪造更新")

    logger.info(f"{_TAG} appid={state.appid} buildid {state.buildid} -> {meta.buildid}，命中 {len(matched)} 个 depot")
    await bot.send(MessageSegment.file(new_text.encode("utf-8"), file_name))
    await bot.send(f"已将游戏 {state.name or state.appid} 的 manifest 文件伪造为最新版本！")


async def _read_upload(ev: Event) -> tuple[str, str]:
    """取上传的 ACF 文本与安全文件名；url 类型经下载器落 cache，读取后即删。"""
    if not ev.file:
        raise ValueError("请附上 appmanifest_xxx.acf 文件执行命令")

    file_name = _safe_name(ev.file_name)
    if not file_name.lower().endswith(_SUFFIX):
        raise ValueError("仅支持 .acf 文件")

    if ev.file.startswith(("http://", "https://")):
        content = await _download_upload(ev.file)
    else:
        content = _decode_upload(ev.file)
    if not content:
        raise ValueError("ACF 文件内容为空")
    return content.decode("utf-8", errors="replace"), file_name


async def _download_upload(url: str) -> bytes:
    """按框架下载器落 cache 后读取；临时文件用完即删。"""
    target = CACHE_DIR / f"{uuid.uuid4().hex}{_SUFFIX}"
    path = await download(url, save_path=target, kind="file")
    if path is None:
        raise ValueError("下载上传的 ACF 文件失败，请重试")
    try:
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _decode_upload(raw: str) -> bytes:
    """base64 上传内容解码；内容非法时给出用户可见错误。"""
    try:
        return base64.b64decode(raw)
    except binascii.Error as error:
        raise ValueError("ACF 文件内容解析失败，请重新上传原始文件") from error


def _safe_name(name: str | None) -> str:
    """只保留文件名本身，并替换对发送端有特殊含义的字符。"""
    cleaned = _UNSAFE_RE.sub("_", Path(name).name) if name is not None else ""
    return cleaned or _DEFAULT_NAME
