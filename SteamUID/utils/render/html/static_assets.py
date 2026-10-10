"""插件自带静态图、字体与数据图缓存的 HTTP 挂载与直链生成。"""

from pathlib import Path

from starlette.types import Scope
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from gsuid_core.config import CONFIG_DEFAULT, core_config
from gsuid_core.app_life import app as fastapi_app
from gsuid_core.data_store import get_res_path

_HTML_DIR = Path(__file__).resolve().parent
TEXTURE2D_DIR = _HTML_DIR / "texture2d"
FONTS_DIR = _HTML_DIR.parent / "fonts"
IMG_CACHE_DIR = get_res_path("SteamUID/img_cache")

DEFAULT_AVATAR_NAME = "default_icon.jpg"

_TEXTURE2D_ROUTE = "/steamuid/texture2d"
_FONTS_ROUTE = "/steamuid/fonts"
_IMG_CACHE_ROUTE = "/steamuid/img_cache"


class _CORSStaticFiles(StaticFiles):
    """附带 CORS 头的静态资源；模板跨源取图与字体需要它。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response


def _base_url() -> str:
    """gsuid_core 本地服务地址；绑定到全网卡时回落到回环地址。"""
    host = str(core_config.get_config("HOST") or CONFIG_DEFAULT["HOST"]).lower()
    port = str(core_config.get_config("PORT") or CONFIG_DEFAULT["PORT"])
    if host in ("", "all", "none", "dual", "0.0.0.0", "0.0.0.0:"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _ensure_mounted() -> None:
    """把自带图 / 字体 / 数据图缓存挂到核心 FastAPI；按路由去重，重复调用不重挂。"""
    mounted = {route.path for route in fastapi_app.routes}
    for route_path, directory, name in (
        (_TEXTURE2D_ROUTE, TEXTURE2D_DIR, "steamuid_texture2d"),
        (_FONTS_ROUTE, FONTS_DIR, "steamuid_fonts"),
        (_IMG_CACHE_ROUTE, IMG_CACHE_DIR, "steamuid_img_cache"),
    ):
        if route_path in mounted or not directory.is_dir():
            continue
        fastapi_app.mount(route_path, _CORSStaticFiles(directory=directory), name=name)


def get_texture_url(name: str) -> str:
    """插件自带静态图直链；图缺失时回落空串。"""
    if not (TEXTURE2D_DIR / name).is_file():
        return ""
    _ensure_mounted()
    return f"{_base_url()}{_TEXTURE2D_ROUTE}/{name}"


def get_font_url(name: str) -> str:
    """插件自带字体直链；字体缺失时回落空串。"""
    if not (FONTS_DIR / name).is_file():
        return ""
    _ensure_mounted()
    return f"{_base_url()}{_FONTS_ROUTE}/{name}"


def get_img_cache_url(name: str) -> str:
    """数据图缓存直链；文件缺失时回落空串。"""
    if not (IMG_CACHE_DIR / name).is_file():
        return ""
    _ensure_mounted()
    return f"{_base_url()}{_IMG_CACHE_ROUTE}/{name}"


def get_default_avatar_url() -> str:
    """默认头像直链；缺失时回落空串（模板侧再兜底）。"""
    return get_texture_url(DEFAULT_AVATAR_NAME)
