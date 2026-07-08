from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.exceptions import SteamError
from .push_service import switch_push

push_SV = SV("steam推送开关")

# (命令关键字, 推送列名, 是否开启)
_PUSH_COMMANDS: list[tuple[tuple[str, ...], list[str], bool]] = [
    (("开启推送",), ["push_start_game", "push_end_game", "push_archivement"], True),
    (("关闭推送",), ["push_start_game", "push_end_game", "push_archivement"], False),
    (("开启开始游戏推送",), ["push_start_game"], True),
    (("关闭开始游戏推送",), ["push_start_game"], False),
    (("开启结束游戏推送",), ["push_end_game"], True),
    (("关闭结束游戏推送",), ["push_end_game"], False),
    (("开启成就推送",), ["push_archivement"], True),
    (("关闭成就推送",), ["push_archivement"], False),
]


def _make_handler(columns: list[str], enabled: bool):
    async def _handler(bot: Bot, ev: Event):
        try:
            steamid64 = ev.text.strip()
            result = await switch_push(ev, steamid64, columns, enabled)
            if result:
                await bot.send(result)
        except SteamError as e:
            await bot.send(str(e))
        except Exception as e:
            logger.exception(f"[SteamPush] 推送开关命令异常: {e}")
            await bot.send("发生未知错误，请稍后重试或联系管理员")

    return _handler


for _cmds, _columns, _enabled in _PUSH_COMMANDS:
    push_SV.on_command(_cmds)(_make_handler(_columns, _enabled))
