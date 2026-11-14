"""ASF IPC 路径常量，不包含请求逻辑。"""

ASF_API_PREFIX = "/Api"
BOT_PREFIX = "/Bot"


def bot_path(bot_name: str) -> str:
    """单个 bot 的资源路径；bot 名由调用方保证已校验。"""
    return f"{BOT_PREFIX}/{bot_name}"


def bot_action_path(bot_name: str, action: str) -> str:
    """bot 子资源路径，如 Input / Start / Rename。"""
    return f"{bot_path(bot_name)}/{action}"
