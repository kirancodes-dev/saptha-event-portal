"""
utils_qr.py

QR code generation helpers for SapthaEvent.

Two functions:
  generate_qr_base64(data)   — returns a base64 PNG string for embedding in HTML/email
  generate_qr_response(data) — returns a Flask Response that serves the PNG directly

Usage in a template:
    <img src="data:image/png;base64,{{ qr_b64 }}" width="200" height="200">

Usage as a route:
    <img src="/ticket/qr/REG-123456">
"""
import io
import base64
import qrcode
from qrcode.image.pil import PilImage
from flask import Response


def generate_qr_base64(data: str, box_size: int = 8, border: int = 2) -> str:
    """
    Generate a QR code for `data` and return it as a base64-encoded PNG string.
    Embed directly in <img src="data:image/png;base64,{{ value }}">

    NOTE: PilImage factory only supports plain color names (black/white),
          not hex strings. Use fill_color="black" — not "#0d2d62".
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def generate_qr_response(data: str, box_size: int = 8, border: int = 2) -> Response:
    """
    Generate a QR code for `data` and return it as a Flask PNG response.
    Use as an <img src="/ticket/qr/<reg_id>"> endpoint.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=86400"}
    )