"""公告正文 BBCode 转 HTML：内嵌媒体先落 img_cache，再以挂载直链拼装。

解析按标签栈进行，支持段落 / 标题 / 列表 / 引用 / 代码 / 链接 / 图片与视频缩略图。
"""

import re
import html
from typing import Literal
from dataclasses import dataclass
from collections.abc import Mapping, Sequence

from ...downloader import download
from .static_assets import get_img_cache_url

# 正文图床宏只给相对路径，需要补 clan CDN 前缀
CLAN_IMAGE_BASE = "https://clan.akamai.steamstatic.com/images"
YOUTUBE_THUMB = "https://img.youtube.com/vi/{vid}/hqdefault.jpg"

_CODE_BLOCK_RE = re.compile(r"(\[code\].*?\[/code\])", re.S | re.I)
_IMG_BODY_RE = re.compile(r"\[img\](.*?)\[/img\]", re.S | re.I)
_URL_BODY_RE = re.compile(r"\[url\]([^\[\]]+?)\[/url\]", re.I)
_YOUTUBE_BODY_RE = re.compile(r"\[youtube\](.*?)\[/youtube\]", re.S | re.I)
_TOKEN_RE = re.compile(r"\[(?P<slash>/?)(?P<name>\*|[a-zA-Z][a-zA-Z0-9]*)(?P<attr>[^\]]*)\]")
_IMG_SRC_RE = re.compile(r"""src\s*=\s*["']?([^"'\]]+)""", re.I)
_HREF_RE = re.compile(r"""href\s*=\s*["']?([^"'\]]+)""", re.I)
_VIDEO_ID_RE = re.compile(r"""[=:"']?\s*([^;"'\]]+)""")

_HEADING_TAGS: dict[str, str] = {"h1": "announce-h1", "h2": "announce-h2", "h3": "announce-h3"}
# 段落级标签：文本落在其中时不再另起段落
_BLOCK_TAGS: tuple[str, ...] = ("p", "li", "h1", "h2", "h3", "blockquote", "pre", "div")


@dataclass(frozen=True)
class _Inline:
    """行内标签的落地写法，css_class 为空时输出裸标签。"""

    tag: str
    css_class: str


_INLINE_TAGS: dict[str, _Inline] = {
    "b": _Inline("strong", ""),
    "i": _Inline("em", ""),
    "u": _Inline("span", "text-underline"),
    "strike": _Inline("del", ""),
    "spoiler": _Inline("span", "spoiler-text"),
}


@dataclass(frozen=True)
class Media:
    """正文里需要落盘的媒体：图片或视频缩略图。"""

    kind: Literal["image", "video"]
    url: str


def _absolute(url: str) -> str:
    """补全图床宏为绝对地址；非 http(s) 一律丢弃，避免渲染出坏链接。"""
    cleaned = url.strip().strip("\"'")
    if not cleaned:
        return ""
    if cleaned.startswith("{STEAM_CLAN_IMAGE}"):
        cleaned = CLAN_IMAGE_BASE + cleaned[len("{STEAM_CLAN_IMAGE}") :]
    elif cleaned.startswith("{STEAM_CLAN_LOC_IMAGE}"):
        cleaned = CLAN_IMAGE_BASE + cleaned[len("{STEAM_CLAN_LOC_IMAGE}") :]
    if not cleaned.lower().startswith(("http://", "https://")):
        return ""
    return cleaned


def _normalize(raw: str) -> str:
    """把变体写法归一成带属性的形式，后续只按一种语法解析。"""
    text = _IMG_BODY_RE.sub(lambda match: f'[img src="{match.group(1)}"]', raw)
    text = _URL_BODY_RE.sub(lambda match: f"[url={match.group(1)}]{match.group(1)}[/url]", text)
    return _YOUTUBE_BODY_RE.sub(lambda match: f"[previewyoutube={match.group(1)}]", text)


def _img_url(attr: str) -> str:
    found = _IMG_SRC_RE.search(attr)
    return _absolute(found.group(1)) if found is not None else ""


def _video_url(attr: str) -> str:
    found = _VIDEO_ID_RE.match(attr)
    return YOUTUBE_THUMB.format(vid=found.group(1)) if found is not None else ""


def _link_href(attr: str) -> str:
    """链接地址：dynamiclink 带 href 属性，普通 url 的属性值就是地址。"""
    found = _HREF_RE.search(attr)
    return _absolute(found.group(1)) if found is not None else _absolute(attr)


def collect_media(raw: str) -> list[Media]:
    """收集正文里全部待落盘媒体，按出现顺序去重。"""
    text = _normalize(raw)
    found: list[Media] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        if match.group("slash"):
            continue
        name = match.group("name").lower()
        attr = match.group("attr").lstrip("=").strip()
        if name == "img":
            url = _img_url(attr)
            if url and url not in seen:
                seen.add(url)
                found.append(Media(kind="image", url=url))
        elif name == "previewyoutube":
            url = _video_url(attr)
            if url and url not in seen:
                seen.add(url)
                found.append(Media(kind="video", url=url))
    return found


async def download_media(items: Sequence[Media]) -> dict[str, str]:
    """并发落盘全部媒体，返回 远程地址 -> 挂载直链；失败项不进结果。"""
    urls = list(dict.fromkeys(item.url for item in items))
    if not urls:
        return {}

    paths = await download(urls, kind="image")
    local: dict[str, str] = {}
    for url, path in zip(urls, paths):
        if path is None:
            continue
        mounted = get_img_cache_url(path.name)
        if mounted:
            local[url] = mounted
    return local


def _pop_until(out: list[str], stack: list[str], *names: str) -> None:
    """按栈收尾到指定标签为止；栈里没有目标标签时不动。"""
    if not any(name in stack for name in names):
        return
    while stack:
        top = stack.pop()
        out.append(f"</{top}>")
        if top in names:
            return


def _drop_empty_p(out: list[str]) -> None:
    """块级元素前若刚闭合了一个空段落，丢弃它，避免多出一条空白。"""
    if len(out) >= 2 and out[-1] == "</p>" and out[-2] == "<p>":
        del out[-2:]


def _media_html(kind: str, url: str) -> str:
    escaped = html.escape(url, quote=True)
    if kind == "video":
        return (
            '<div class="content-media-wrapper"><div class="youtube-preview">'
            f'<img class="content-img" src="{escaped}" alt="">'
            '<div class="video-play-badge">▶ 视频预览</div>'
            "</div></div>"
        )
    return f'<div class="content-media-wrapper"><img class="content-img" src="{escaped}" alt=""></div>'


def _code_html(block: str) -> str:
    inner = block[len("[code]") : -len("[/code]")]
    return f'<pre class="announce-code">{html.escape(inner.strip())}</pre>'


def _open_paragraph(out: list[str], stack: list[str], chunk: str) -> None:
    """裸文本：落在段落级标签里直接写，否则先补一个段落。"""
    if not any(tag in stack for tag in _BLOCK_TAGS):
        out.append("<p>")
        stack.append("p")
    out.append(html.escape(chunk))


def _render_segment(text: str, local: Mapping[str, str], out: list[str], stack: list[str]) -> None:
    position = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() > position:
            _open_paragraph(out, stack, text[position : match.start()])
        position = match.end()
        _render_token(match, local, out, stack)
    if position < len(text):
        _open_paragraph(out, stack, text[position:])


def _render_token(match: re.Match[str], local: Mapping[str, str], out: list[str], stack: list[str]) -> None:
    closing = bool(match.group("slash"))
    name = match.group("name").lower()
    attr = match.group("attr").lstrip("=").strip().strip("\"'")

    if name == "*":
        if closing:
            _pop_until(out, stack, "li")
            return
        _pop_until(out, stack, "li", "p")
        if "ul" not in stack:
            out.append('<ul class="announce-list">')
            stack.append("ul")
        out.append("<li>")
        stack.append("li")
        return

    if name in ("list", "olist"):
        if closing:
            _pop_until(out, stack, "li", "p", "ul")
            return
        _pop_until(out, stack, "p")
        if "ul" not in stack:
            out.append('<ul class="announce-list">')
            stack.append("ul")
        return

    if name in _HEADING_TAGS:
        if closing:
            _pop_until(out, stack, name)
            return
        _pop_until(out, stack, "p", "h1", "h2", "h3")
        out.append(f'<{name} class="{_HEADING_TAGS[name]}">')
        stack.append(name)
        return

    if name == "p":
        if closing:
            _pop_until(out, stack, "p")
            return
        _pop_until(out, stack, "p")
        out.append("<p>")
        stack.append("p")
        return

    if name in _INLINE_TAGS:
        inline = _INLINE_TAGS[name]
        if closing:
            _pop_until(out, stack, inline.tag)
            return
        if inline.css_class:
            out.append(f'<{inline.tag} class="{inline.css_class}">')
        else:
            out.append(f"<{inline.tag}>")
        stack.append(inline.tag)
        return

    if name == "quote":
        if closing:
            _pop_until(out, stack, "blockquote")
            return
        _pop_until(out, stack, "p")
        out.append('<blockquote class="announce-quote">')
        stack.append("blockquote")
        return

    if name in ("url", "dynamiclink"):
        if closing:
            _pop_until(out, stack, "a")
            return
        href = _link_href(attr)
        out.append(f'<a class="announce-link" href="{html.escape(href, quote=True)}">')
        stack.append("a")
        return

    if name in ("img", "previewyoutube"):
        _pop_until(out, stack, "p")
        _drop_empty_p(out)
        if name == "img":
            url = _img_url(match.group("attr"))
            kind = "image"
        else:
            url = _video_url(match.group("attr"))
            kind = "video"
        if url and url in local:
            out.append(_media_html(kind, local[url]))
        return

    if name == "hr":
        _pop_until(out, stack, "p")
        _drop_empty_p(out)
        out.append('<hr class="announce-hr">')


def to_html(raw: str, local: Mapping[str, str]) -> str:
    """按已落盘媒体映射拼装正文 HTML；未落盘成功的媒体直接丢弃。"""
    text = _normalize(raw)
    out: list[str] = []
    stack: list[str] = []
    position = 0
    for match in _CODE_BLOCK_RE.finditer(text):
        if match.start() > position:
            _render_segment(text[position : match.start()], local, out, stack)
        out.append(_code_html(match.group(1)))
        position = match.end()
    if position < len(text):
        _render_segment(text[position:], local, out, stack)

    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


async def build_content_html(raw: str) -> str:
    """公告正文转 HTML：先把内嵌媒体落盘，再拼装正文。"""
    local = await download_media(collect_media(raw))
    return to_html(raw, local)
