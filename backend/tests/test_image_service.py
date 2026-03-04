import io
from unittest.mock import MagicMock, AsyncMock

from PIL import Image as PILImage

from app.models import Image, ImagePurchase
from app.services.image import generate_etag, user_has_access_to_image, _create_thumbnail_sync


def _make_image(sha512="abc123"):
    img = MagicMock(spec=Image)
    img.sha512_hash = sha512
    return img


def test_generate_etag_full_vs_watermarked():
    image = _make_image()
    etag_full = generate_etag(image, has_access=True)
    etag_wm = generate_etag(image, has_access=False)
    assert etag_full != etag_wm
    assert isinstance(etag_full, str)


def test_generate_etag_deterministic():
    image = _make_image()
    assert generate_etag(image, True) == generate_etag(image, True)


async def test_user_has_access_true():
    db = AsyncMock()
    result_mock = MagicMock()
    purchase = MagicMock(spec=ImagePurchase)
    result_mock.scalars.return_value.first.return_value = purchase
    db.execute.return_value = result_mock

    assert await user_has_access_to_image(db, user_id=1, image_id=1) is True


async def test_user_has_access_false():
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute.return_value = result_mock

    assert await user_has_access_to_image(db, user_id=1, image_id=999) is False


def test_create_thumbnail_sync():
    img = PILImage.new("RGB", (500, 500), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    thumb_bytes = _create_thumbnail_sync(image_bytes)
    thumb = PILImage.open(io.BytesIO(thumb_bytes))
    assert thumb.width <= 200
    assert thumb.height <= 200
    assert thumb.format == "JPEG"
