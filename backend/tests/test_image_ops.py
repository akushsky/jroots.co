from unittest.mock import AsyncMock, MagicMock, patch

from backend import crud

def get_mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.scalar = AsyncMock()
    db.get = AsyncMock()
    return db

@patch("backend.crud.PILImage.open")
@patch("backend.crud.ImageOps.exif_transpose")
async def test_save_unique_image_creates_new(mock_exif, mock_open):
    # Mock image processing
    mock_image = MagicMock()
    mock_image.convert.return_value = mock_image
    mock_exif.return_value = mock_image
    mock_open.return_value = mock_image

    mock_image.thumbnail = MagicMock()
    mock_image.save = MagicMock(side_effect=lambda buf, format: buf.write(b"thumbnail"))

    # Mock DB
    db = get_mock_db()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalar_one.return_value = "new_image_object"
    db.execute.return_value = result_mock

    result = await crud.save_unique_image(
        db=db,
        image_path="image.jpg",
        image_key="key123",
        image_source_id=1,
        image_binary=b"binaryimagecontent"
    )

    assert result == "new_image_object"
    db.add.assert_called_once()
    db.commit.assert_called_once()



async def test_save_unique_image_reuses_existing():
    db = AsyncMock()

    # Mock db.execute().scalar_one_or_none()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = "existing_image"
    db.execute.return_value = execute_result

    result = await crud.save_unique_image(
        db=db,
        image_path="img.jpg",
        image_key="k",
        image_source_id=None,
        image_binary=b"samebinary"
    )

    assert result == "existing_image"
    db.add.assert_not_called()
    db.commit.assert_not_called()


async def test_create_search_object_success():
    db = get_mock_db()

    result_mock = MagicMock()
    result_mock.scalar_one.return_value = "search_obj"
    db.execute.return_value = result_mock

    result = await crud.create_search_object(db, "some text", 300, image_id=42)

    assert result == "search_obj"
    db.add.assert_called_once()
    db.commit.assert_called_once()
