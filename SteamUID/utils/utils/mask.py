"""通用打码：把 id 中间部分替换为星号。"""


def mask_id(text: str) -> str:
    """保留首字符与末两位，中间替换为星号；长度不足 4 时整体打码。"""
    if len(text) < 4:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 3) + text[-2:]
