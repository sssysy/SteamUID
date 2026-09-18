"""Steam 文本 VDF（appmanifest ACF）解析与字段改写"""

from __future__ import annotations

from typing import Any

from ..exceptions import SteamValidationError


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "{":
            tokens.append("{")
            i += 1
            continue
        if ch == "}":
            tokens.append("}")
            i += 1
            continue
        if ch == '"':
            i += 1
            buf: list[str] = []
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                buf.append(c)
                i += 1
            tokens.append("".join(buf))
            continue
        # 非引号裸 token（少数 ACF 变体）
        start = i
        while i < n and (not text[i].isspace()) and text[i] not in '{}"':
            i += 1
        tokens.append(text[start:i])
    return tokens


def _parse_object(tokens: list[str], idx: int) -> tuple[dict[str, Any], int]:
    obj: dict[str, Any] = {}
    while idx < len(tokens):
        key = tokens[idx]
        if key == "}":
            return obj, idx + 1
        idx += 1
        if idx >= len(tokens):
            raise SteamValidationError("ACF 文件格式不完整")
        value = tokens[idx]
        if value == "{":
            child, idx = _parse_object(tokens, idx + 1)
            obj[key] = child
        else:
            obj[key] = value
            idx += 1
    return obj, idx


def parse_acf(text: str) -> dict[str, Any]:
    """解析 ACF 文本，返回顶层 dict（通常为 {"AppState": {...}}）"""
    tokens = _tokenize(text)
    if not tokens:
        raise SteamValidationError("ACF 文件为空")
    root, _ = _parse_object(tokens, 0)
    return root


def get_app_state(root: dict[str, Any]) -> dict[str, Any]:
    state = root.get("AppState")
    if not isinstance(state, dict):
        raise SteamValidationError("ACF 缺少 AppState 字段")
    return state


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _dump_object(obj: dict[str, Any], indent: int) -> list[str]:
    pad = "\t" * indent
    lines: list[str] = []
    for key, value in obj.items():
        if isinstance(value, dict):
            lines.append(f'{pad}"{_escape(str(key))}"')
            lines.append(f"{pad}{{")
            lines.extend(_dump_object(value, indent + 1))
            lines.append(f"{pad}}}")
        else:
            lines.append(f'{pad}"{_escape(str(key))}"\t\t"{_escape(str(value))}"')
    return lines


def dumps_acf(root: dict[str, Any]) -> str:
    """序列化为 Steam 风格文本 VDF"""
    lines = _dump_object(root, 0)
    return "\n".join(lines) + "\n"


def apply_latest_manifest(
    root: dict[str, Any],
    *,
    buildid: str,
    depot_manifests: dict[str, str],
) -> list[str]:
    """改写 ACF"""
    state = get_app_state(root)
    state["StateFlags"] = "4"
    state["DownloadType"] = "4"
    state["buildid"] = str(buildid)

    updated: list[str] = []
    installed = state.get("InstalledDepots")
    if not isinstance(installed, dict):
        return updated

    for depot_id, depot in installed.items():
        if not isinstance(depot, dict):
            continue
        gid = depot_manifests.get(str(depot_id))
        if not gid:
            continue
        depot["manifest"] = str(gid)
        updated.append(str(depot_id))
    return updated
