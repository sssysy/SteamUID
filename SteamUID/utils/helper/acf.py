"""appmanifest ACF（Steam 文本 VDF）读取与最小改写。

按行定位目标字段，只替换命中的值，其余字节原样保留，避免整文件重建造成格式漂移。
"""

from __future__ import annotations

import re
from typing import Literal
from dataclasses import dataclass
from collections.abc import Mapping

AcfLineKind = Literal["leaf", "block", "open", "close", "other"]

# 键与值都是可带转义的双引号串，块名单独占一行且后跟 {
_LEAF_RE = re.compile(r'^(?P<indent>[ \t]*)"(?P<key>(?:[^"\\]|\\.)*)"(?P<sep>[ \t]+)"(?P<value>(?:[^"\\]|\\.)*)"$')
_KEY_RE = re.compile(r'^(?P<indent>[ \t]*)"(?P<key>(?:[^"\\]|\\.)*)"$')
_ESCAPE_RE = re.compile(r"\\(.)")

APP_STATE = "AppState"
INSTALLED_DEPOTS = "InstalledDepots"

# 伪造更新：标记为已完整安装，且不再处于待下载状态
FAKE_STATE_FLAGS = "4"
FAKE_DOWNLOAD_TYPE = "4"


@dataclass(frozen=True)
class AcfLine:
    """一行 ACF 文本及其所处块路径；raw 保留原始行（含行尾）。"""

    index: int
    kind: AcfLineKind
    path: tuple[str, ...]
    key: str
    value: str
    raw: str


@dataclass(frozen=True)
class AppStateInfo:
    """AppState 中供伪造更新使用的字段，缺失时为空值。"""

    appid: str
    name: str
    buildid: str
    installed_depots: dict[str, str]


def _unescape(value: str) -> str:
    """还原 ACF 文本里的反斜杠转义。"""
    return _ESCAPE_RE.sub(r"\1", value)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _scan(text: str) -> list[AcfLine]:
    """扫描每行并记录其块路径，路径不含该行自身打开的块。"""
    lines: list[AcfLine] = []
    stack: list[str] = []
    pending = ""
    for index, raw in enumerate(text.splitlines(keepends=True)):
        body = raw.rstrip("\r\n")
        content = body.strip()

        if content == "{":
            lines.append(AcfLine(index, "open", tuple(stack), "", "", raw))
            stack.append(pending)
            pending = ""
            continue

        if content == "}":
            if stack:
                stack.pop()
            lines.append(AcfLine(index, "close", tuple(stack), "", "", raw))
            pending = ""
            continue

        leaf = _LEAF_RE.match(body)
        if leaf is not None:
            key = _unescape(leaf["key"])
            lines.append(AcfLine(index, "leaf", tuple(stack), key, _unescape(leaf["value"]), raw))
            pending = ""
            continue

        key_line = _KEY_RE.match(body)
        if key_line is not None:
            pending = _unescape(key_line["key"])
            lines.append(AcfLine(index, "block", tuple(stack), pending, "", raw))
            continue

        lines.append(AcfLine(index, "other", tuple(stack), "", "", raw))
        pending = ""
    return lines


def _is_installed_depot(line: AcfLine) -> bool:
    return len(line.path) == 3 and line.path[:2] == (APP_STATE, INSTALLED_DEPOTS)


def read_app_state(text: str) -> AppStateInfo:
    """读取 appid / name / buildid 与 InstalledDepots 下各 depot 的 manifest。"""
    appid = ""
    name = ""
    buildid = ""
    installed: dict[str, str] = {}
    for line in _scan(text):
        if line.kind != "leaf":
            continue
        if line.path == (APP_STATE,):
            if line.key == "appid":
                appid = line.value
            elif line.key == "name":
                name = line.value
            elif line.key == "buildid":
                buildid = line.value
        elif line.key == "manifest" and _is_installed_depot(line):
            installed[line.path[2]] = line.value
    return AppStateInfo(appid=appid, name=name, buildid=buildid, installed_depots=installed)


def apply_latest_build(
    text: str,
    *,
    buildid: str,
    depot_manifests: Mapping[str, str],
) -> tuple[str, tuple[str, ...]]:
    """把 buildid / StateFlags / DownloadType 与已安装 depot 的 manifest 改写为最新。

    返回改写后的文本与命中的 depot id；ACF 中缺失的字段不新建。
    """
    lines = text.splitlines(keepends=True)
    matched: list[str] = []
    for line in _scan(text):
        if line.kind != "leaf":
            continue

        target: str | None = None
        if line.path == (APP_STATE,):
            if line.key == "buildid":
                target = buildid
            elif line.key == "StateFlags":
                target = FAKE_STATE_FLAGS
            elif line.key == "DownloadType":
                target = FAKE_DOWNLOAD_TYPE
        elif line.key == "manifest" and _is_installed_depot(line):
            depot_id = line.path[2]
            if depot_id in depot_manifests:
                target = depot_manifests[depot_id]
                matched.append(depot_id)

        if target is None or target == line.value:
            continue
        lines[line.index] = _replace_value(line.raw, target)

    return "".join(lines), tuple(matched)


def _replace_value(raw: str, value: str) -> str:
    """只替换叶子行的值，保留缩进、键转义、分隔符与行尾。"""
    body = raw.rstrip("\r\n")
    terminator = raw[len(body) :]
    match = _LEAF_RE.match(body)
    if match is None:
        return raw
    return f'{match["indent"]}"{match["key"]}"{match["sep"]}"{_escape(value)}"{terminator}'
