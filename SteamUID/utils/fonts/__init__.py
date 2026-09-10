import base64
from pathlib import Path
from typing import Optional

FONTS_DIR: Path = Path(__file__).parent

# 内存缓存已转换的 Base64 Data URI，避免重复读取与编码
_FONT_DATA_URIS: dict[str, str] = {}


def get_font_path(filename: str) -> Path:
    """获取本地字体文件完整路径"""
    return FONTS_DIR / filename


def get_font_data_uri(filename: str) -> Optional[str]:
    """获取指定本地字体的 Base64 Data URI（带内存缓存）。

    例如: get_font_data_uri("steam-Regular.ttf")
    返回: "data:font/ttf;base64,..."
    """
    if filename not in _FONT_DATA_URIS:
        font_path = FONTS_DIR / filename
        if font_path.is_file():
            data = font_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            ext = font_path.suffix.lower()
            mime = "font/ttf" if ext == ".ttf" else ("font/woff2" if ext == ".woff2" else "font/woff")
            _FONT_DATA_URIS[filename] = f"data:{mime};base64,{b64}"
        else:
            return None
    return _FONT_DATA_URIS.get(filename)
