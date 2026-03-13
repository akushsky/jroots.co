import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image import save_unique_image, create_search_object


def get_mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.scalar = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
@patch("app.services.image._save_to_disk", return_value=("/tmp/test.jpg", "/tmp/test_thumb.jpg"))
@patch("app.services.image._create_thumbnail_sync", return_value=b"thumbnail")
async def test_save_unique_image_reuses_existing(mock_thumb, mock_disk):
    db = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "existing_image"
    db.execute.return_value = execute_result

    result = await save_unique_image(
        db=db,
        image_path="img.jpg",
        image_key="k",
        image_source_id=None,
        image_binary=b"samebinary",
    )

    assert result == "existing_image"
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_search_object_success():
    db = get_mock_db()

    result_mock = MagicMock()
    result_mock.scalar_one.return_value = "search_obj"
    db.execute.return_value = result_mock

    result = await create_search_object(db, "some text", image_id=42)

    assert result == "search_obj"
    db.add.assert_called_once()
    db.commit.assert_called_once()
