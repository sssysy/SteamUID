import json
from typing import Dict
from pathlib import Path

import aiofiles
from PIL import Image
from gsuid_core.sv import get_plugin_available_prefix
from gsuid_core.help.model import PluginHelp
from gsuid_core.help.draw_new_plugin_help import get_new_help
from gsuid_core.help.utils import register_help
from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.logger import logger

from ..version import steamUID_version

ICON = Path(__file__).parent.parent.parent / 'ICON.png'
HELP_DATA = Path(__file__).parent / 'help.json'
ICON_PATH = Path(__file__).parent / 'icon_path'
TEXT_PATH = Path(__file__).parent / 'texture2d'

# 使用Core内置函数`get_plugin_available_prefix`获取插件可用的前缀
PREFIX = get_plugin_available_prefix('steamUID')

sv_steam_help = SV('steam帮助')

# 使用aiofiles异步读取help.json文件
async def get_help_data() -> Dict[str, PluginHelp]:
    async with aiofiles.open(HELP_DATA, 'rb') as file:
        return json.loads(await file.read())


async def get_steam_help(user_pm: int):
    return await get_new_help(
        # 插件名
        plugin_name='steamUID',
        # 插件的badge, 会出现在帮助图title的右边的色块
        # 该值是一个dict, key为内容, value为色块颜色（RGB数组或者字符串）
        plugin_info={f'v{steamUID_version}': ''},
        # 插件的logo
        plugin_icon=Image.open(ICON),
        # 之前准备的help.json文件
        plugin_help=await get_help_data(),
        # 插件的前缀, 哪怕存在用户自定义, 也可以让帮助图可以给出正确的命令
        plugin_prefix=PREFIX,
        # 主题, 暂时只影响整体的文字颜色, 如果是dark, 文字则为白色, light则为黑色
        help_mode='dark',
        # 帮助图最上面的部分, 一些精彩的插画非常适合, 注意处理宽度为1545
        banner_bg=Image.open(TEXT_PATH / 'banner_bg.jpg'),
        # 帮助图最上面部分的副标题, 可以写一些个性化内容
        banner_sub_text='Ciallo～(∠・ω< )⌒★',
        # 帮助图背景, 注意处理宽度为1545! 
        # 请尽量使用纯色背景, 如果是插画, 尽量添加高斯模糊或者颜色遮罩!
        help_bg=Image.open(TEXT_PATH / 'bg.jpg'),
        # 分类的横幅, 注意处理宽度为1545! 
        cag_bg=Image.open(TEXT_PATH / 'cag_bg.png'),
        # 单个命令的底部图片, 大小为490x175
        item_bg=Image.open(TEXT_PATH / 'item.png'),
        # 命令图标包, 大小为150x150
        icon_path=ICON_PATH,
        # 页脚图片, 大小为490x175
        footer=Image.open(TEXT_PATH / 'footer.png'),
        # 是否允许缓存, 或者每次使用命令均重新绘制（建议使用缓存）
        enable_cache=True,
        # 为了让不同权限等级，触发帮助的人展现不同的帮助菜单，需要传递ev.user_pm中的权限信息
        pm=user_pm,
    )

register_help('steamUID', f'{PREFIX}帮助', Image.open(ICON))



@sv_steam_help.on_command(("帮助", "help"))
async def send_help_img(bot: Bot, ev: Event) -> None:
    logger.info("开始执行 [steam帮助]")
    user_pm = ev.user_pm
    try:
        image_bytes = await get_steam_help(user_pm)

        await bot.send(image_bytes)
    except Exception as e:
        logger.warning(f"帮助图渲染失败，降级到文本: {e}")
        await bot.send(_fallback_text())


def _fallback_text() -> str:
    """图片渲染失败时的纯文本降级"""
    return """【SteamUID 帮助】
steam绑定 (<steamid>)
steam解绑 (<steamid>)
steam查看
"""