"""绑定列表卡片的组装与渲染。

放渲染层的原因同 push.py：组装卡片要用模板与静态资源直链，helper 不能反向引用 render。
"""

import asyncio
from collections.abc import Sequence

from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..downloader import download
from ..helper.bind import get_binds, session_ids, is_logged_in
from ..helper.config import hide_id
from .html.bind_list import BindCardItem, render_bind_list
from ..helper.command import sender_text
from ..helper.profile import load_profile_assets
from ..helper.steamid import steamid64_to_friend_code
from .html.static_assets import get_img_cache_url, get_default_avatar_url
from ..database.model_bind import SteamBind

_TAG = "[Steam·账户绑定]"


async def _resolve_qq_avatar(ev: Event) -> str:
    """群聊头像经 downloader 落 img_cache 后取直链，缺失回落默认头像。"""
    url = sender_text(ev, "avatar")
    if url.startswith(("http://", "https://")):
        path = await download(url, kind="image")
        if path is not None:
            return get_img_cache_url(path.name)
    return get_default_avatar_url()


async def _load_card_item(bind: SteamBind, group_id: str, *, force: bool = False) -> BindCardItem:
    """组装单个药丸数据；资料抓取失败时回落默认昵称与头像，不影响其它账户。"""
    profile, logged_in = await asyncio.gather(
        load_profile_assets(bind.steamid64, force=force),
        is_logged_in(bind.steamid64),
        return_exceptions=True,
    )

    if isinstance(profile, BaseException):
        logger.warning(f"{_TAG} 卡片资料获取失败 {bind.steamid64}: {profile!r}")
        name = hide_id(bind.steamid64)
        friend_code = steamid64_to_friend_code(bind.steamid64)
        avatar_url = get_default_avatar_url()
        frame_url = ""
        background_url = ""
    else:
        name = profile.name
        friend_code = profile.friend_code
        avatar_url = get_img_cache_url(profile.avatar_name) or get_default_avatar_url()
        frame_url = get_img_cache_url(profile.frame_name)
        background_url = get_img_cache_url(profile.background_name)

    if isinstance(logged_in, BaseException):
        logger.warning(f"{_TAG} 登录状态查询失败 {bind.steamid64}: {logged_in!r}")
        login_state = False
    else:
        login_state = logged_in

    return BindCardItem(
        name=name,
        friend_code=friend_code,
        avatar_url=avatar_url,
        frame_url=frame_url,
        background_url=background_url,
        is_main=bool(bind.is_main_id and bind.group_id == group_id),
        is_login=login_state,
    )


async def _build_card_items(binds: Sequence[SteamBind], group_id: str, *, force: bool = False) -> list[BindCardItem]:
    return list(await asyncio.gather(*(_load_card_item(bind, group_id, force=force) for bind in binds)))


async def render_bind_card_image(ev: Event, user_id: str, *, force: bool = False) -> bytes:
    """渲染该会话内 user_id 的绑定列表卡片（与 steam查看 同款）；force 为真时重下资料图片。"""
    binds = await get_binds(ev, user_id)
    items = await _build_card_items(binds, session_ids(ev)[2], force=force)
    user_name = sender_text(ev, "nickname") or user_id
    qq_avatar_url = await _resolve_qq_avatar(ev)
    return await render_bind_list(items, user_name=user_name, qq_avatar_url=qq_avatar_url)
