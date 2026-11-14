"""ASF IPC 资源级 API：只做请求与 JSON 解码，不承担业务编排。"""

import json
from typing import TypedDict
from collections.abc import Mapping

from .client import AsfEndpoint, request_asf
from .models import AsfBot, AsfEUserInputType, AsfBotInputRequest, AsfBotConfigRequest
from .endpoints import bot_path, bot_action_path


class AsfGenericResponse(TypedDict):
    """无 Result 的普通响应，如写配置、提交输入、启动停止。"""

    Success: bool
    Message: str | None


class AsfBotMapResponse(TypedDict):
    """带 Result 的 bot 列表响应。"""

    Success: bool
    Message: str | None
    Result: dict[str, object]


def _encode(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _decode_bot_map(content: bytes) -> dict[str, AsfBot]:
    payload: AsfBotMapResponse = json.loads(content)
    if not payload["Success"]:
        raise ValueError("ASF 返回失败")
    bots: dict[str, AsfBot] = {}
    for name, raw in payload["Result"].items():
        bots[name] = _read_bot(name, raw)
    return bots


def _read_bot(name: str, raw: object) -> AsfBot:
    if not isinstance(raw, dict):
        raise ValueError("ASF bot 结构异常")
    bot_config = raw["BotConfig"]
    if not isinstance(bot_config, dict):
        raise ValueError("ASF bot 配置结构异常")
    return AsfBot(
        BotName=str(raw["BotName"]),
        BotConfig={str(key): value for key, value in bot_config.items()},
        RequiredInput=int(raw["RequiredInput"]),
        QrChallengeURL=_optional_str(raw["QrChallengeURL"]),
        IsConnectedAndLoggedOn=bool(raw["IsConnectedAndLoggedOn"]),
        HasMobileAuthenticator=bool(raw["HasMobileAuthenticator"]),
        SteamID=raw["SteamID"],
    )


def _optional_str(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("ASF 字段类型异常")
    return raw


async def get_bots(endpoint: AsfEndpoint, bot_names: str = "ASF") -> dict[str, AsfBot]:
    """读取 bot 状态；bot_names 支持 ASF 的复数语法与 steamid。"""
    response = await request_asf(endpoint, "GET", bot_path(bot_names))
    return _decode_bot_map(response.content)


async def update_bot_config(
    endpoint: AsfEndpoint,
    bot_name: str,
    bot_config: Mapping[str, object],
) -> None:
    """整份写回 BotConfig；调用方必须先拉取并合并原配置。"""
    payload: AsfBotConfigRequest = {"BotConfig": dict(bot_config)}
    response = await request_asf(
        endpoint,
        "POST",
        bot_path(bot_name),
        content=_encode(payload),
    )
    result: AsfGenericResponse = json.loads(response.content)
    if not result["Success"]:
        raise ValueError("ASF 写回 BotConfig 失败")


async def send_input(
    endpoint: AsfEndpoint,
    bot_name: str,
    input_type: AsfEUserInputType,
    value: str,
) -> None:
    """向 bot 提交一次输入，例如扫码选择 Y。"""
    payload: AsfBotInputRequest = {"Type": int(input_type), "Value": value}
    response = await request_asf(
        endpoint,
        "POST",
        bot_action_path(bot_name, "Input"),
        content=_encode(payload),
    )
    result: AsfGenericResponse = json.loads(response.content)
    if not result["Success"]:
        raise ValueError("ASF 拒绝接收输入")


async def start_bot(endpoint: AsfEndpoint, bot_name: str) -> None:
    """启动 bot；已在运行时 ASF 会直接返回成功。"""
    await _post_action(endpoint, bot_action_path(bot_name, "Start"))


async def stop_bot(endpoint: AsfEndpoint, bot_name: str) -> None:
    """停止 bot。"""
    await _post_action(endpoint, bot_action_path(bot_name, "Stop"))


async def rename_bot(endpoint: AsfEndpoint, bot_name: str, new_name: str) -> None:
    """重命名 bot，ASF 会连同 BotName.db 一并迁移。"""
    payload: dict[str, str] = {"NewName": new_name}
    await _post_action(
        endpoint,
        bot_action_path(bot_name, "Rename"),
        content=_encode(payload),
    )


async def pause_bot(endpoint: AsfEndpoint, bot_name: str) -> None:
    """暂停挂卡；保留用户后续手动 resume 的能力。"""
    payload: dict[str, object] = {"Permanent": False, "ResumeInSeconds": 0}
    await _post_action(
        endpoint,
        bot_action_path(bot_name, "Pause"),
        content=_encode(payload),
    )


async def _post_action(
    endpoint: AsfEndpoint,
    path: str,
    *,
    content: bytes | None = None,
) -> None:
    response = await request_asf(endpoint, "POST", path, content=content)
    result: AsfGenericResponse = json.loads(response.content)
    if not result["Success"]:
        raise ValueError("ASF 操作失败")
