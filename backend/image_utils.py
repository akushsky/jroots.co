import hashlib

import PIL
from PIL import Image, ImageFont, ImageDraw

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
async def generate_etag(buffer, has_access):
    image_bytes = buffer.getvalue()
    to_hash = image_bytes[:4096] if len(image_bytes) > 4096 else image_bytes
    # Generate ETag based on access + image hash
    data_hash = hashlib.sha256(to_hash).hexdigest()
    access_key = "full" if has_access else "watermarked"
    etag = f'{access_key}-{data_hash}'
    return etag
