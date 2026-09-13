import asyncio
import base64
import hashlib
import re
from pathlib import Path
from typing import List, Sequence, Union, overload

import httpx
from gsuid_core.data_store import get_res_path
from gsuid_core.logger import logger

CACHE_DIR: Path = get_res_path("SteamUID") / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_VALID_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".webm",
    ".mp4",
    ".mp3",
    ".wav",
    ".svg",
    ".ttf",
    ".woff",
    ".woff2",
}


def get_cache_path(url: str, save_dir: Path | str | None = None) -> Path:
    """根据 URL 计算本地缓存文件路径：md5(url) + 原始后缀。

    同一 URL 恒定映射到同一路径，可据此判断缓存是否命中；
    后缀非法（无后缀 / 带 query 的未知后缀）时统一按 .jpg 处理。
    """
    target_dir = Path(save_dir) if save_dir is not None else CACHE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    clean_url = url.split("?")[0].split("#")[0]
    ext = Path(clean_url).suffix.lower()
    if ext not in _VALID_EXTENSIONS:
        ext = ".jpg"

    stem = hashlib.md5(url.encode("utf-8")).hexdigest()
    return target_dir / f"{stem}{ext}"


async def _download_single(
    client: httpx.AsyncClient,
    url: str,
    target_path: Path,
    force: bool = False,
) -> Path | None:
    """下载单个文件并保存到指定路径。"""
    if not url or not url.strip():
        return None

    # 本地已有缓存且不强制刷新时，直接返回
    if not force and target_path.is_file() and target_path.stat().st_size > 0:
        return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content = resp.content
        if not content:
            logger.warning(f"[SteamUID] 下载资源内容为空: {url}")
            return None
        target_path.write_bytes(content)
        return target_path
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"[SteamUID] 下载资源未找到 (404): {url}")
        else:
            logger.warning(
                f"[SteamUID] 下载资源失败 HTTP {e.response.status_code}: {url}"
            )
        return None
    except httpx.TimeoutException:
        logger.warning(f"[SteamUID] 下载资源超时: {url}")
        return None
    except Exception as e:
        logger.warning(f"[SteamUID] 下载资源异常: {url}, 错误: {e!r}")
        return None


@overload
async def download(
    target: str,
    save_dir: Path | str | None = None,
    *,
    save_path: Path | str | None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> Path | None: ...


@overload
async def download(
    target: Sequence[str],
    save_dir: Path | str | None = None,
    *,
    save_path: None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> List[Path | None]: ...


async def download(
    target: Union[str, Sequence[str]],
    save_dir: Path | str | None = None,
    *,
    save_path: Path | str | None = None,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    force: bool = False,
) -> Union[Path, None, List[Union[Path, None]]]:
    """统一资源下载函数，支持单文件 / 多文件并发限制下载，自动判定本地缓存"""
    if isinstance(target, str):
        url = target.strip()
        if not url:
            return None

        dest_path = (
            Path(save_path)
            if save_path is not None
            else get_cache_path(url, save_dir=save_dir)
        )

        # 检查本地缓存
        if not force and dest_path.is_file() and dest_path.stat().st_size > 0:
            return dest_path

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await _download_single(client, url, dest_path, force=force)

    # 批量下载处理
    urls = list(target)
    if not urls:
        return []

    results: List[Path | None] = [None] * len(urls)
    sem = asyncio.Semaphore(max_concurrency)

    async def _worker(client: httpx.AsyncClient, index: int, u: str) -> None:
        if not u or not u.strip():
            results[index] = None
            return

        dest = get_cache_path(u.strip(), save_dir=save_dir)
        # 本地已有缓存则不占并发槽位直接记录
        if not force and dest.is_file() and dest.stat().st_size > 0:
            results[index] = dest
            return

        async with sem:
            # 二次检测防止并发重复写入
            if not force and dest.is_file() and dest.stat().st_size > 0:
                results[index] = dest
                return
            results[index] = await _download_single(
                client, u.strip(), dest, force=force
            )

    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(
            *[_worker(client, i, u) for i, u in enumerate(urls)]
        )

    return results


_HTML_RES_URL_PATTERN = re.compile(
    r"""(?i)(?:src|href|background|url)\s*=\s*['"](https?://[^'"]+)['"]|url\(\s*['"]?(https?://[^'")]+)['"]?\s*\)"""
)


_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def _file_to_data_uri(file_path: Path) -> str | None:
    """将本地文件转为 Data URI (Base64)"""
    try:
        data = file_path.read_bytes()
        ext = file_path.suffix.lower()
        mime = _MIME_TYPES.get(ext, "application/octet-stream")
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.debug(f"[SteamUID] 文件转 Base64 失败 {file_path}: {e}")
        return None


_FONT_REF_PATTERN = re.compile(
    r"/fonts/([A-Za-z0-9_.\-]+\.(?:ttf|woff2?|otf))", re.IGNORECASE
)


def _replace_local_fonts(html_content: str) -> str:
    """将模板/CSS 中的 /fonts/<文件名> 引用替换为本地字体的 Base64 Data URI"""
    if "/fonts/" not in html_content:
        return html_content

    from .fonts import get_font_data_uri

    def _to_data_uri(match: re.Match) -> str:
        data_uri = get_font_data_uri(match.group(1))
        return data_uri if data_uri else match.group(0)

    return _FONT_REF_PATTERN.sub(_to_data_uri, html_content)


_RENDER_CSS_DIR: Path = Path(__file__).parent / "render" / "css"
_CSS_CACHE: dict[str, str] = {}
_CSS_LINK_PATTERN = re.compile(
    r'<link\b(?=[^>]*\brel=["\']stylesheet["\'])(?=[^>]*\bhref=["\']([^"\']+\.css)["\'])[^>]*>',
    re.IGNORECASE,
)


def _inline_local_css(html_content: str) -> str:
    """自动扫描 HTML 中的本地 CSS 链接并内联为 <style> 标签，支持内存缓存。"""
    if "<link" not in html_content:
        return html_content

    def _replace_link(match: re.Match) -> str:
        css_href = match.group(1)
        filename = Path(css_href).name
        if filename not in _CSS_CACHE:
            css_file = _RENDER_CSS_DIR / filename
            if css_file.is_file():
                _CSS_CACHE[filename] = css_file.read_text(encoding="utf-8")
            else:
                return match.group(0)  # 文件不存在保持原样
        css_content = _CSS_CACHE[filename]
        return f"<style>\n/* Inlined: {filename} */\n{css_content}\n</style>"

    try:
        return _CSS_LINK_PATTERN.sub(_replace_link, html_content)
    except Exception as e:
        logger.debug(f"[SteamUID] 内联本地 CSS 异常: {e}")
        return html_content


async def replace_html_urls_with_local(
    html_content: str,
    *,
    save_dir: Path | str | None = None,
    max_concurrency: int = 8,
    timeout: float = 15.0,
) -> str:
    """自动扫描 HTML/CSS 中的网络静态资源 URL，使用 downloader 下载到本地并替换为 Base64 Data URI"""
    if not html_content:
        return html_content

    # 0. 优先内联本地 CSS 样式文件
    html_content = _inline_local_css(html_content)

    # 0.5 优先替换 Motiva Sans 本地字体（避免网络请求或 404）
    html_content = _replace_local_fonts(html_content)

    # 1. 匹配所有 http(s) 链接
    matches = _HTML_RES_URL_PATTERN.findall(html_content)
    raw_urls: set[str] = set()
    for m in matches:
        for u in m:
            if u and u.startswith(("http://", "https://")):
                raw_urls.add(u)

    if not raw_urls:
        return html_content

    url_list = list(raw_urls)
    # 2. 并发批量下载
    local_paths = await download(
        url_list,
        save_dir=save_dir,
        max_concurrency=max_concurrency,
        timeout=timeout,
    )

    # 3. 替换 HTML 中的 URL 为 Base64 Data URI
    replaced_html = html_content
    for u, p in zip(url_list, local_paths):
        if p is not None and p.is_file() and p.stat().st_size > 0:
            data_uri = _file_to_data_uri(p)
            if data_uri:
                replaced_html = replaced_html.replace(u, data_uri)

    return replaced_html

