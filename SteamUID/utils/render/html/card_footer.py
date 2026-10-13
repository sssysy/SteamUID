"""卡片页脚组件：所有卡片共用的署名行。

样式固定在 common.css 的 .card-footer 段，使用方只允许覆盖内外边距，
新增卡片一律复用本模块，禁止再各抄一份 HTML 或 CSS。
"""


def footer_html() -> str:
    """拼装署名页脚 HTML；高亮只变色，字重与正文一致。"""
    return (
        '<div class="card-footer">'
        'Create by <span class="footer-highlight">GsCore</span> &amp; '
        'Power by <span class="footer-highlight">SteamUID</span>'
        "</div>"
    )
