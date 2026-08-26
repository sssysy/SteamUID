import html as html_lib
import re

STEAM_CLAN_IMAGE_CDN = "https://clan.akamai.steamstatic.com/images"


def steam_bbcode_to_html(bbcode_text: str) -> str:
    """将 Steam 官方公告的所有 BBCode 富文本元素精准转换为美观规范的 HTML。"""
    if not bbcode_text:
        return ""

    text = bbcode_text

    # 1. 替换 Steam 内部图片宏
    text = text.replace("{STEAM_CLAN_IMAGE}", STEAM_CLAN_IMAGE_CDN)
    text = text.replace("{STEAM_CLAN_LOC_IMAGE}", STEAM_CLAN_IMAGE_CDN)

    # 2. 处理图片（同时支持 [img src="..."]、[img src=...]、[img]...[/img]、[img=...] 等各种变体）
    # 2.1 带属性的 [img ... src="url" ...] 或 [img="url"]
    def _parse_img_tag(match):
        full_tag = match.group(0)
        src_match = re.search(r'(?:src=|=)\s*["\']?([^"\'\]\s>]+)', full_tag, re.IGNORECASE)
        if src_match:
            url = src_match.group(1).strip()
            return f'<div class="content-media-wrapper"><img class="content-img" src="{url}" alt=""></div>'
        return ""

    text = re.sub(
        r'\[img\s+[^\]]*?\](?:\[/img\])?|\[img=[^\]]+\](?:\[/img\])?',
        _parse_img_tag,
        text,
        flags=re.IGNORECASE,
    )

    # 2.2 常规 [img]URL[/img]
    def _parse_img_body(match):
        url = match.group(1).strip()
        if url:
            return f'<div class="content-media-wrapper"><img class="content-img" src="{url}" alt=""></div>'
        return ""

    text = re.sub(
        r'\[img\](.*?)\[/img\]',
        _parse_img_body,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # 3. 处理 YouTube 视频 [previewyoutube="ID;full"][/previewyoutube] / [youtube]ID[/youtube]
    def _parse_youtube(match):
        raw_val = match.group(1).strip().strip('"\'')
        vid_info = raw_val.split(";")
        vid_id = vid_info[0].strip().strip('"\'')
        if vid_id:
            thumb_url = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
            return (
                f'<div class="content-media-wrapper">'
                f'<div class="youtube-preview">'
                f'<img class="content-img" src="{thumb_url}" alt="YouTube Video">'
                f'<div class="video-play-badge">▶ 视频预览</div>'
                f'</div></div>'
            )
        return ""

    text = re.sub(
        r'\[previewyoutube=(?:["\'])?([^"\'\]]+)(?:["\'])?\](?:\[/previewyoutube\])?',
        _parse_youtube,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\[youtube\](.*?)\[/youtube\]',
        _parse_youtube,
        text,
        flags=re.IGNORECASE,
    )

    # 4. 处理标题 [h1], [h2], [h3]
    text = re.sub(r'\[h1\](.*?)\[/h1\]', r'<h1 class="announce-h1">\1</h1>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[h2\](.*?)\[/h2\]', r'<h2 class="announce-h2">\1</h2>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[h3\](.*?)\[/h3\]', r'<h3 class="announce-h3">\1</h3>', text, flags=re.IGNORECASE | re.DOTALL)

    # 5. 处理段落 [p ...](.*?)[/p] 及单独残留的 [p ...] / [/p]
    text = re.sub(r'\[p(?:\s+[^\]]*)?\](.*?)\[/p\]', r'<div class="announce-p">\1</div>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[/?p(?:\s+[^\]]*)?\]', '', text, flags=re.IGNORECASE)

    # 6. 处理分割线 [hr] / [hr][/hr]
    text = re.sub(r'\[hr\](?:\[/hr\])?', r'<hr class="announce-hr">', text, flags=re.IGNORECASE)

    # 7. 处理链接 [url="..."]...[/url] / [url=...]...[/url] / [dynamiclink href="..."]...[/dynamiclink] / [dynamiclink]
    def _parse_url(match):
        raw_url = match.group(1).strip().strip('"\'')
        label = match.group(2).strip() or raw_url
        return f'<span class="announce-link">{label}</span>'

    text = re.sub(r'\[url=(?:["\'])?([^"\'\]]+)(?:["\'])?\](.*?)\[/url\]', _parse_url, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[url\](.*?)\[/url\]', r'<span class="announce-link">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[dynamiclink(?:\s+href=(?:["\'])?([^"\'\]]*)(?:["\'])?)?\](.*?)\[/dynamiclink\]', r'<span class="announce-link">\2</span>', text, flags=re.IGNORECASE | re.DOTALL)

    # 8. 处理样式标签 [b], [i], [u], [strike], [spoiler]
    text = re.sub(r'\[b\](.*?)\[/b\]', r'<strong>\1</strong>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[i\](.*?)\[/i\]', r'<em>\1</em>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[u\](.*?)\[/u\]', r'<span class="text-underline">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[strike\](.*?)\[/strike\]', r'<del>\1</del>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[spoiler\](.*?)\[/spoiler\]', r'<span class="spoiler-text">\1</span>', text, flags=re.IGNORECASE | re.DOTALL)

    # 9. 处理引用与代码块 [quote], [code]
    text = re.sub(r'\[quote(?:=[^\]]*)?\](.*?)\[/quote\]', r'<blockquote class="announce-quote">\1</blockquote>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[code\](.*?)\[/code\]', r'<pre class="announce-code"><code>\1</code></pre>', text, flags=re.IGNORECASE | re.DOTALL)

    # 10. 处理列表 [list] / [olist] / [*] / [/*]
    def _parse_list(match):
        content = match.group(1)
        content = re.sub(r'\[/\*\]', '', content, flags=re.IGNORECASE)
        items = re.split(r'\[\*\]', content)
        li_parts = []
        for it in items:
            it_clean = it.strip()
            if it_clean:
                li_parts.append(f'<li>{it_clean}</li>')
        return f'<ul class="announce-list">{"".join(li_parts)}</ul>'

    text = re.sub(r'\[list\](.*?)\[/list\]', _parse_list, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[olist\](.*?)\[/olist\]', _parse_list, text, flags=re.IGNORECASE | re.DOTALL)

    # 11. 处理表格 [table] / [tr] / [th] / [td]
    text = re.sub(r'\[table\](.*?)\[/table\]', r'<table class="announce-table">\1</table>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[tr\](.*?)\[/tr\]', r'<tr>\1</tr>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[th\](.*?)\[/th\]', r'<th>\1</th>', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[td\](.*?)\[/td\]', r'<td>\1</td>', text, flags=re.IGNORECASE | re.DOTALL)

    # 12. 处理折叠/展开 [expand=...]...[/expand] / [expand]...[/expand]
    text = re.sub(r'\[expand(?:=[^\]]*)?\](.*?)\[/expand\]', r'<div class="announce-expand">\1</div>', text, flags=re.IGNORECASE | re.DOTALL)

    # 13. 兜底清理所有形如 [xxx] 或 [/xxx] 的残留 BBCode 标签
    text = re.sub(r'\[/?[a-zA-Z0-9_\-=:\";/ .#?&%]+\]', '', text)

    # 14. 处理换行：清理多余重复换行并转换 \n 为 <br>
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('\n', '<br>')

    # 15. 清除块级标签周围多余的 <br>
    text = re.sub(r'(</(?:h1|h2|h3|blockquote|pre|ul|ol|div|table|tr|th|td|hr)>)<br>', r'\1', text)
    text = re.sub(r'<br>(<(?:h1|h2|h3|blockquote|pre|ul|ol|div|table|tr|th|td|hr))', r'\1', text)

    return text
