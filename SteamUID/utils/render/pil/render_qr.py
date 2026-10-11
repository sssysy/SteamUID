"""扫码登录二维码的 PIL 渲染。"""

from io import BytesIO

# Steam 主色橙底白背，与插件其它图文风格一致
_QR_COLOR = (255, 134, 36)
_BOX_SIZE = 10
_BORDER = 4


async def render_qr_png(content: str) -> bytes:
    """把 content 画成 PNG 二维码字节，版本由 qrcode 按内容长度自适应。"""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L
    from qrcode.image.pil import PilImage

    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_L,
        box_size=_BOX_SIZE,
        border=_BORDER,
    )
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(fill_color=_QR_COLOR, back_color="white")
    if not isinstance(image, PilImage):
        raise RuntimeError("二维码渲染结果类型异常")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
