import io

import PIL
import pytest
from PIL import Image

from app.services.image import apply_watermark


@pytest.fixture
def sample_rgba_image():
    return Image.new("RGBA", (200, 200), color=(255, 0, 0, 255))


def image_to_bytes(pil_image: PIL.Image.Image) -> bytes:
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_apply_watermark_returns_valid_image(sample_rgba_image):
    watermarked = await apply_watermark(sample_rgba_image)

    assert isinstance(watermarked, PIL.Image.Image)
    assert watermarked.size == sample_rgba_image.size

    original_bytes = image_to_bytes(sample_rgba_image.convert("RGB"))
    watermarked_bytes = image_to_bytes(watermarked)
    assert original_bytes != watermarked_bytes
