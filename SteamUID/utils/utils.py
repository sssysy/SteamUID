import asyncio
import hashlib
from pathlib import Path
from typing import List
from gsuid_core.logger import logger

import httpx


async def batch_download_images(
    urls: List[str],
    save_dir: str,
    max_concurrency: int = 5,
) -> List[str | None]:
    """批量下载图片"""
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(max_concurrency)
    paths: List[str | None] = [None] * len(urls)

    async with httpx.AsyncClient(timeout=60) as client:

        async def _download(index: int, url: str) -> None:
            async with sem:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    content = resp.content
                    md5 = hashlib.md5(content).hexdigest()
                    ext = Path(url).suffix or ".jpg"
                    file_path = save_path / f"{md5}{ext}"
                    if not file_path.exists():
                        file_path.write_bytes(content)
                    paths[index] = str(file_path)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"未找到当前图片: {url}")
                    else:
                        logger.warning(f"下载图片失败: {url}")
                        logger.warning(f"错误信息: {e}")
                    paths[index] = None
                except Exception as e:
                    logger.warning(f"下载图片失败: {url}")
                    logger.warning(f"错误信息: {e}")
                    paths[index] = None

        await asyncio.gather(
            *[_download(i, url) for i, url in enumerate(urls)]
        )

    return paths


_BASE_STEAM_ID64 = 76561197960265728


def steamid64_to_friend_code(steamid64: str) -> str:
    """将 steamid64 转换为好友码（账号ID）"""
    return str(int(steamid64) - _BASE_STEAM_ID64)


def auto2steamid64(count: str | None) -> str | None:
    """把好友码/steamid64自动变化成steamid64"""
    if count is None or count.strip() == "" or not count.isdigit():
        return None
    count = count.strip()
    if int(count) < _BASE_STEAM_ID64:
        count = str(_BASE_STEAM_ID64 + int(count))
    return count

def HideStr(text: str) -> str:
    """12345678 -> 1*****78"""
    if len(text) < 4:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 3) + text[-2:]


def maybe_hide_steamid(text: str) -> str:
    """根据 HideSteamID 配置决定是否对 steamid / 好友码套用 HideStr"""
    from ..SteamConfig import SteamConfig
    if SteamConfig.get_config("HideSteamID").data:
        return HideStr(text)
    return text
