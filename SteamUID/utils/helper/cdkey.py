"""Steam CDKey 解析：切分、规整补连字符、格式校验与结果码文案。"""

import re

# 标准激活码：15 位 (5-5-5) 与 25 位 (5-5-5-5-5)，仅大写字母与数字
_CDKEY_PATTERN = re.compile(r"^(?:[A-Z0-9]{5}-){2}[A-Z0-9]{5}$|^(?:[A-Z0-9]{5}-){4}[A-Z0-9]{5}$")

# 激活结果码 → 用户可见原因；未收录的码由调用方回落成通用文案
RESULT_REASONS: dict[int, str] = {
    9: "已拥有该产品",
    13: "缺少本体游戏 / 前置 DLC",
    14: "无效的代码",
    15: "已被其他账户兑换",
    24: "地区限制(锁区)",
    53: "尝试失败过多被限频",
}


def split_cdkeys(text: str) -> list[str]:
    """按空格 / 半角逗号 / 全角逗号 / 换行切分，丢弃空片段并保持原序。"""
    return [token for token in re.split(r"[,，\s]+", text) if token]


def normalize_cdkey(raw: str) -> str | None:
    """规整单枚 CDKey：大写去空，无连字符时按 15 / 25 位补连字符。

    不满足标准格式返回 None，由调用方决定如何提示与中止。
    """
    key = raw.strip().upper()
    if "-" not in key:
        if len(key) == 15:
            key = f"{key[:5]}-{key[5:10]}-{key[10:]}"
        elif len(key) == 25:
            key = f"{key[:5]}-{key[5:10]}-{key[10:15]}-{key[15:20]}-{key[20:]}"
    return key if _CDKEY_PATTERN.match(key) else None
