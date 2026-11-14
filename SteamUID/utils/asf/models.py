"""ASF IPC 响应结构与输入枚举，只声明插件消费的字段。"""

from enum import IntEnum
from typing import TypedDict


class AsfErrorBody(TypedDict, total=False):
    Message: str


class AsfEUserInputType(IntEnum):
    """ASF 的 EUserInputType；只保留插件会发送的取值。"""

    LOGIN = 1
    PASSWORD = 2
    STEAM_GUARD = 3
    STEAM_PARENTAL_CODE = 4
    TWO_FACTOR_AUTHENTICATION = 5
    CRYPTKEY = 6
    DEVICE_CONFIRMATION = 7
    QR_CODE_LOGIN = 8


class AsfEOlineStatus(IntEnum):
    """ASF 的 EPersonaState；插件登录时固定使用 Invisible。"""

    OFFLINE = 0
    ONLINE = 1
    BUSY = 2
    AWAY = 3
    SNOOZE = 4
    LOOKING_TO_TRADE = 5
    LOOKING_TO_PLAY = 6
    INVISIBLE = 7


class AsfEFarmingPreferences(IntEnum):
    """EFarmingPreferences 的位标志；只声明插件会读写的位。"""

    NONE = 0
    FARMING_PAUSED_BY_DEFAULT = 1


class AsfBot(TypedDict):
    """GET /Api/Bot/{botNames} 返回的 bot 状态。"""

    BotName: str
    BotConfig: dict[str, object]
    RequiredInput: int
    QrChallengeURL: str | None
    IsConnectedAndLoggedOn: bool
    HasMobileAuthenticator: bool
    SteamID: int | str


class AsfBotInputRequest(TypedDict):
    Type: int
    Value: str


class AsfBotConfigRequest(TypedDict):
    """POST /Api/Bot/{botNames} 的请求体。"""

    BotConfig: dict[str, object]
