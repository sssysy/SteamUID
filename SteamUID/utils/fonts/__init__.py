import base64
from pathlib import Path
from typing import Optional

FONTS_DIR: Path = Path(__file__).parent

_FONT_DATA_URIS: dict[str, str] = {}


def get_font_path(filename: str) -> Path:
    return FONTS_DIR / filename


def get_font_data_uri(filename: str) -> Optional[str]:
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
