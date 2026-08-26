import html as html_lib
import re

# Steam 官方 CDN 图片前缀常量
STEAM_CLAN_IMAGE_CDN = "https://clan.akamai.steamstatic.com/images"


def steam_bbcode_to_html(bbcode_text: str) -> str:
    """将 Steam 公告的 BBCode 富文本转换为美观的 HTML。"""
    if not bbcode_text:
        return ""

    text = bbcode_text

    # 1. 替换 Steam 内部图片宏
    text = text.replace("{STEAM_CLAN_IMAGE}", STEAM_CLAN_IMAGE_CDN)
    text = text.replace("{STEAM_CLAN_LOC_IMAGE}", STEAM_CLAN_IMAGE_CDN)

    # 2. HTML 转义基础文本，避免注入
    text = html_lib.escape(text)

    # 3. 处理 YouTube 视频占位 [previewyoutube=VIDEO_ID;...][/previewyoutube]
    def _replace_youtube(match):
        vid_info = match.group(1).split(";")
        vid_id = vid_info[0]
        thumb_url = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
        return (
            f'<div class="content-media-wrapper">'
            f'<div class="youtube-preview">'
            f'<img class="content-img" src="{thumb_url}" alt="YouTube Video">'
            f'<div class="video-play-badge">▶ 视频预览</div>'
            f'</div></div>'
        )

    text = re.sub(
        r"\[previewyoutube=([^\]]+)\](?:\[/previewyoutube\])?",
        _replace_youtube,
        text,
        flags=re.IGNORECASE,
    )

    # 4. 处理图片 [img]URL[/img]
    def _replace_img(match):
        img_url = match.group(1).strip()
        return (
            f'<div class="content-media-wrapper">'
            f'<img class="content-img" src="{img_url}" alt="" loading="lazy">'
            f'</div>'
        )

    text = re.sub(
        r"\[img\](.*?)\[/img\]",
        _replace_img,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 5. 处理标题 [h1], [h2], [h3]
    text = re.sub(r"\[h1\](.*?)\[/h1\]", r'<h1 class="announce-h1">\1</h1>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[h2\](.*?)\[/h2\]", r'<h2 class="announce-h2">\1</h2>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[h3\](.*?)\[/h3\]", r'<h3 class="announce-h3">\1</h3>', text, flags=re.IGNORECASE | re.DOTALL)

    # 6. 处理常用排版标签 [b], [i], [u], [strike], [spoiler]
    text = re.sub(r"\[b\](.*?)\[/b\]", r'<strong>\1</strong>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[i\](.*?)\[/i\]", r'<em>\1</em>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[u\](.*?)\[/u\]", r'<span class="text-underline">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[strike\](.*?)\[/strike\]", r'<del>\1</del>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[spoiler\](.*?)\[/spoiler\]", r'<span class="spoiler-text">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)

    # 7. 处理引用与代码块 [quote], [code]
    text = re.sub(r"\[quote(?:=[^\]]*)?\](.*?)\[/quote\]", r'<blockquote class="announce-quote">\1</blockquote>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[code\](.*?)\[/code\]", r'<pre class="announce-code"><code>\1</code></pre>', text, flags=re.IGNORECASE | re.DOTALL)

    # 8. 处理链接 [url=...]...[/url] / [url]...[/url]
    text = re.sub(r"\[url=([^\]]+)\](.*?)\[/url\]", r'<span class="announce-link">\2</span>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[url\](.*?)\[/url\]", r'<span class="announce-link">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)

    # 9. 处理列表 [list] / [olist] / [*]
    def _parse_list(match):
        content = match.group(1)
        items = re.split(r"\[\*\]", content)
        li_parts = []
        for it in items:
            it_clean = it.strip()
            if it_clean:
                li_parts.append(f"<li>{it_clean}</li>")
        return f'<ul class="announce-list">{"".join(li_parts)}</ul>'

    text = re.sub(r"\[list\](.*?)\[/list\]", _parse_list, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\[olist\](.*?)\[/olist\]", _parse_list, text, flags=re.IGNORECASE | re.DOTALL)

    # 10. 处理换行：清理多余的重复换行并转换 \n 为 <br>
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("\n", "<br>")

    # 清除由于块级标签包裹产生的无意义多余 <br>
    text = re.sub(r"(</(?:h1|h2|h3|blockquote|pre|ul|ol|div)>)<br>", r"\1", text)
    text = re.sub(r"<br>(<(?:h1|h2|h3|blockquote|pre|ul|ol|div))", r"\1", text)

    return text
