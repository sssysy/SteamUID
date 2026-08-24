import io
import asyncio
from datetime import datetime

import httpx
from PIL import Image
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.segment import MessageSegment
from gsuid_core.logger import logger

from ..SteamConfig import SteamConfig
from ..utils.api import get_user_year_in_review_share_images, get_user_Summaries
from ..utils.database.models import SteamBind
from ..utils.utils import auto2steamid64
from ..utils.exceptions import SteamValidationError, SteamAPIError


year_review_sv = SV("steam年度回顾相关")


def _get_usage_msg() -> str:
    prefix = get_plugin_available_prefix("SteamUID")
    return f"[SteamUID] 参数错误！正确用法：{prefix}年度回顾 [年份]\n如: {prefix}年度回顾2025"


@year_review_sv.on_command("年度回顾")
async def get_year_review(bot: Bot, ev: Event):
    try:
        usage_msg = _get_usage_msg()
        steamid64: str | None = None
        year: int = datetime.now().year - 1

        # 1. 检查是否 @他人
        if ev.at:
            if not SteamConfig.get_config("AllowAt").data:
                raise SteamValidationError("未开启 @ 他人获取他人信息功能")

            steamid64 = await SteamBind.get_main_id(
                ev.bot_id, ev.at, ev.user_type, ev.group_id
            )
            if not steamid64:
                raise SteamValidationError("该用户尚未绑定 steam 账号")

            text = ev.text.strip()
            if text:
                tokens = text.split()
                if len(tokens) == 1 and len(tokens[0]) == 4 and tokens[0].isdigit():
                    parsed_year = int(tokens[0])
                    if parsed_year < 2022:
                        raise SteamValidationError(usage_msg)
                    year = parsed_year
                else:
                    raise SteamValidationError(usage_msg)
        else:
            text = ev.text.strip()
            tokens = text.split() if text else []

            if len(tokens) == 0:
                # 默认发送者绑定账号，年份为当前年份 - 1
                year = datetime.now().year - 1
                steamid64 = await SteamBind.get_main_id(
                    ev.bot_id, ev.user_id, ev.user_type, ev.group_id
                )
                if not steamid64:
                    raise SteamValidationError("请先绑定 steam 账号，或输入 好友码/SteamID")
            elif len(tokens) == 1:
                token = tokens[0]
                if len(token) == 4 and token.isdigit():
                    # 仅提供年份
                    parsed_year = int(token)
                    if parsed_year < 2022:
                        raise SteamValidationError(usage_msg)
                    year = parsed_year
                    steamid64 = await SteamBind.get_main_id(
                        ev.bot_id, ev.user_id, ev.user_type, ev.group_id
                    )
                    if not steamid64:
                        raise SteamValidationError("请先绑定 steam 账号，或输入 好友码/SteamID")
                else:
                    # 仅提供 好友码/SteamID64
                    steamid64 = auto2steamid64(token)
                    if not steamid64:
                        raise SteamValidationError(usage_msg)
                    year = datetime.now().year - 1
            elif len(tokens) == 2:
                t1, t2 = tokens[0], tokens[1]
                t1_is_year = len(t1) == 4 and t1.isdigit()
                t2_is_year = len(t2) == 4 and t2.isdigit()

                if t1_is_year and not t2_is_year:
                    year_token, id_token = t1, t2
                elif t2_is_year and not t1_is_year:
                    year_token, id_token = t2, t1
                else:
                    raise SteamValidationError(usage_msg)

                parsed_year = int(year_token)
                if parsed_year < 2022:
                    raise SteamValidationError(usage_msg)
                year = parsed_year

                steamid64 = auto2steamid64(id_token)
                if not steamid64:
                    raise SteamValidationError(usage_msg)
            else:
                raise SteamValidationError(usage_msg)

        # 2. 调用 API 获取年度回顾分享图片链接
        image_urls = await get_user_year_in_review_share_images(steamid64, year)
        if not image_urls:
            steamuser = steamid64
            try:
                players = await get_user_Summaries(steamid64)
                if players and players[0].get("personaname"):
                    steamuser = players[0]["personaname"]
            except Exception:
                pass
            await bot.send(f"[SteamUID] {steamuser} 的 {year} 年年度回顾未公开")
            return

        # 3. 并发下载所有分享图片
        async def fetch_img(client: httpx.AsyncClient, url: str) -> bytes | None:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.content
            except Exception as e:
                logger.warning(f"[SteamUID] 下载年度回顾图片失败 {url}: {e}")
            return None

        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [fetch_img(client, url) for url in image_urls]
            img_data_list = await asyncio.gather(*tasks)

        valid_img_data = [data for data in img_data_list if data]
        if not valid_img_data:
            steamuser = steamid64
            try:
                players = await get_user_Summaries(steamid64)
                if players and players[0].get("personaname"):
                    steamuser = players[0]["personaname"]
            except Exception:
                pass
            await bot.send(f"[SteamUID] {steamuser} 的 {year} 年年度回顾未公开")
            return

        # 4. 使用 PIL 处理并按上下顺序拼接图片
        pil_images: list[Image.Image] = []
        for data in valid_img_data:
            try:
                im = Image.open(io.BytesIO(data))
                pil_images.append(im.convert("RGBA"))
            except Exception as e:
                logger.warning(f"[SteamUID] 解析年度回顾图片异常: {e}")

        if not pil_images:
            steamuser = steamid64
            try:
                players = await get_user_Summaries(steamid64)
                if players and players[0].get("personaname"):
                    steamuser = players[0]["personaname"]
            except Exception:
                pass
            await bot.send(f"[SteamUID] {steamuser} 的 {year} 年年度回顾未公开")
            return

        if len(pil_images) == 1:
            out_io = io.BytesIO()
            pil_images[0].save(out_io, format="PNG")
            await bot.send(MessageSegment.image(out_io.getvalue()))
            return

        # 多张图片垂直上下无缝拼接
        max_width = max(img.width for img in pil_images)
        resized_imgs: list[Image.Image] = []
        for img in pil_images:
            if img.width != max_width:
                new_height = int(img.height * (max_width / img.width))
                resized_imgs.append(img.resize((max_width, new_height), Image.Resampling.LANCZOS))
            else:
                resized_imgs.append(img)

        total_height = sum(img.height for img in resized_imgs)
        canvas = Image.new("RGBA", (max_width, total_height), (255, 255, 255, 0))
        current_y = 0
        for img in resized_imgs:
            canvas.paste(img, (0, current_y))
            current_y += img.height

        out_io = io.BytesIO()
        canvas.save(out_io, format="PNG")
        await bot.send(MessageSegment.image(out_io.getvalue()))

    except SteamValidationError as e:
        await bot.send(str(e))
    except SteamAPIError as e:
        await bot.send(str(e))
    except Exception as e:
        logger.exception(f"[SteamYearReview] 年度回顾命令异常: {e!r}")
        await bot.send("发生未知错误，详情请查看后台。")
