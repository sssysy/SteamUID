"""ASF IPC 响应结构声明。"""

from typing import TypedDict


class AsfErrorBody(TypedDict, total=False):
    Message: str
