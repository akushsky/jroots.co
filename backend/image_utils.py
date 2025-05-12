import base64
import hashlib
import hmac

import PIL
from PIL import Image, ImageFont, ImageDraw

import models
from config import SECRET_KEY


# This function applies a watermark to an image.
async def apply_watermark(original):
    watermark = PIL.Image.new("RGBA", original.size, (255, 255, 255, 0))

    # Font setup
    font_size = max(original.width // 20, 30)  # Slightly smaller font, denser watermark
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    watermark_text = "JRoots.co"
    opacity = 150  # Semi-transparent for multiple layers

    # Create watermark image (rotated)
    single_watermark = PIL.Image.new("RGBA", (font_size * len(watermark_text), font_size + 10), (255, 255, 255, 0))
    single_draw = ImageDraw.Draw(single_watermark)
    single_draw.text((0, 0), watermark_text, font=font, fill=(255, 255, 255, opacity))

    # Rotate watermark
    angle = 30  # degrees
    rotated_watermark = single_watermark.rotate(angle, expand=True)

    # Adjust spacing for denser coverage
    spacing_x = rotated_watermark.width
    spacing_y = rotated_watermark.height // 2

    # Tiled watermark placement (denser pattern)
    for x in range(-rotated_watermark.width, original.width + rotated_watermark.width, spacing_x):
        for y in range(-rotated_watermark.height, original.height + rotated_watermark.height, spacing_y):
            watermark.alpha_composite(rotated_watermark, (x, y))

    # Combine watermark with the original image
    watermarked = PIL.Image.alpha_composite(original, watermark).convert("RGB")
    return watermarked


# Generate ETag based on image data
async def generate_etag(image: models.Image, has_access: bool) -> str:
    # Generate ETag based on access + image hash
    access_key = "full" if has_access else "watermarked"
    etag = f'{access_key}-{image.sha512_hash}'
    return sign_etag(etag)

def sign_etag(payload: str) -> str:
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest()
    # Base64-encode to make it HTTP-header safe
    return base64.urlsafe_b64encode(signature).decode()