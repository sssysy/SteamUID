"""Steam 帮助命令：help.json 驱动的帮助图注册与绘制。"""

from typing import NamedTuple, NotRequired
from pathlib import Path

import msgspec
from PIL import Image

from gsuid_core.sv import SV, get_plugin_available_prefix
from gsuid_core.bot import Bot
from gsuid_core.pool import to_thread
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.help.model import PluginHelp
from gsuid_core.help.utils import register_help
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import version
from ..utils.helper.command import command_guard

_HELP_DIR = Path(__file__).resolve().parent
_HELP_DATA = _HELP_DIR / "help.json"
TEXTURE_PATH = _HELP_DIR / "texture2d"
ICON_PATH = _HELP_DIR / "icon_path"
# 插件 logo 直接取插件根目录的 ICON.png，不再单独生成一份
ICON = _HELP_DIR.parent.parent / "ICON.png"

# 帮助图 banner 副标题，一句话概括插件能力
_BANNER_SUB_TEXT = "全功能 Steam 插件"

PREFIX = get_plugin_available_prefix("SteamUID")

steam_help_sv = SV("Steam帮助")


class _Category(PluginHelp):
    """框架 PluginHelp 加可选 pm，帮助图据此对普通用户隐藏管理类分类。"""

    pm: NotRequired[int]


class _Textures(NamedTuple):
    """帮助图素材集合，均来自 steam_help/texture2d。"""

    icon: Image.Image
    banner: Image.Image
    bg: Image.Image
    cag: Image.Image
    item: Image.Image
    footer: Image.Image


# 超管 pm 阈值：与旧分类 pm 一致，pm 越小可见范围越大
_ADMIN_PM = 1


@to_thread
def _load_help_data(pm: int) -> dict[str, PluginHelp]:
    """读 help.json，滤掉当前用户看不到的分类与需要超管的条目。"""
    categories = msgspec.json.decode(_HELP_DATA.read_bytes(), type=dict[str, _Category])
    visible: dict[str, PluginHelp] = {}
    for name, category in categories.items():
        if "pm" in category and pm > category["pm"]:
            continue
        # 框架只按分类级 pm 过滤，条目级超管标记只能在这里剔除
        data = [item for item in category["data"] if pm <= _ADMIN_PM or not item["need_admin"]]
        visible[name] = {"desc": category["desc"], "data": data}
    return visible


@to_thread
def _load_textures() -> _Textures:
    """加载帮助图素材；PIL 解码是阻塞操作，统一放线程里。"""
    return _Textures(
        icon=Image.open(ICON).convert("RGBA"),
        banner=Image.open(TEXTURE_PATH / "banner_bg.jpg").convert("RGBA"),
        bg=Image.open(TEXTURE_PATH / "bg.png").convert("RGBA"),
        cag=Image.open(TEXTURE_PATH / "cag_bg.png").convert("RGBA"),
        item=Image.open(TEXTURE_PATH / "item.png").convert("RGBA"),
        footer=Image.open(TEXTURE_PATH / "footer.png").convert("RGBA"),
    )


async def get_help(pm: int) -> str | bytes:
    """绘制本插件帮助图；pm 为触发者的权限等级，返回图片字节或 base64 串。"""
    textures = await _load_textures()
    return await get_new_help(
        plugin_name="SteamUID",
        plugin_info={f"v{version}": ""},
        plugin_icon=textures.icon,
        plugin_help=await _load_help_data(pm),
        plugin_prefix=PREFIX,
        icon_path=ICON_PATH,
        banner_bg=textures.banner,
        banner_sub_text=_BANNER_SUB_TEXT,
        help_bg=textures.bg,
        cag_bg=textures.cag,
        item_bg=textures.item,
        footer=textures.footer,
        column=4,
        pm=pm,
    )


@steam_help_sv.on_fullmatch("帮助", block=True)
@command_guard
async def steam_help(bot: Bot, ev: Event) -> None:
    """steam帮助：绘制 SteamUID 全部命令的帮助图。"""
    await bot.send(MessageSegment.image(await get_help(ev.user_pm)))


register_help("SteamUID", f"{PREFIX}帮助", Image.open(ICON))
