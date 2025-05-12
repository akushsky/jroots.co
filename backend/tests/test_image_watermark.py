import io

import PIL
import pytest
from PIL import Image

from backend.image_utils import apply_watermark  # Adjust the import to match your structure


@pytest.fixture
def sample_rgba_image():
    # Create a 200x200 transparent RGBA image with a solid red rectangle
    img = Image.new('RGBA', (200, 200), color=(255, 0, 0, 255))
    return img


@pytest.mark.asyncio
async def test_apply_watermark_returns_valid_image(sample_rgba_image):
    watermarked = await apply_watermark(sample_rgba_image)

    # Ensure the result is an image
    assert isinstance(watermarked, PIL.Image.Image), "Expected result to be a PIL Image"

    # Ensure result size matches original
    assert watermarked.size == sample_rgba_image.size, "Watermarked image size should match original"

    # Ensure watermarked image is different from the original by comparing pixel data
    original_bytes = image_to_bytes(sample_rgba_image.convert("RGB"))
    watermarked_bytes = image_to_bytes(watermarked)

    assert original_bytes != watermarked_bytes, "Watermarked image content should differ from original"


def image_to_bytes(pil_image: PIL.Image.Image) -> bytes:
    """Utility to convert PIL image to bytes."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()
