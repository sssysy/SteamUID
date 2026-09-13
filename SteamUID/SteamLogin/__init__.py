from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from . import web_router  # 触发 FastAPI Web 路由挂载
from .login_service import request_web_login
from ..utils.helpers.command import steam_command

login_sv = SV("Steam登录")


@steam_command("SteamLogin", fallback="登录请求发生异常，详情请查看后台日志。")
@login_sv.on_command(("登录", "登陆", "login"))
async def steam_login(bot: Bot, ev: Event):
    """
    处理「steam 登录」命令
    生成 WebAuth 网页授权登录链接，引导用户在浏览器中完成账号密码及 2FA 认证
    """
    await request_web_login(bot, ev)
