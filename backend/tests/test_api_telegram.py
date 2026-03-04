from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from sqlalchemy import select

from app.models import ImagePurchase
from tests.conftest import create_user, create_image_record, auth_header


async def test_request_access_unauthenticated(client, db_session):
    image = await create_image_record(db_session)
    response = await client.post("/api/request_access", json={
        "image_id": image.id, "search_text_content": "test",
    })
    assert response.status_code == 403


async def test_request_access_unverified(client, db_session):
    user = await create_user(db_session, is_verified=False)
    response = await client.post(
        "/api/request_access",
        json={"image_id": 1, "search_text_content": "test"},
        headers=auth_header(user),
    )
    assert response.status_code == 403


async def test_request_access_success(client, db_session):
    user = await create_user(db_session, telegram_username="tguser")
    image = await create_image_record(db_session)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": {"photo": [{"file_id": "fid"}]}}

    with patch("app.routers.telegram.send_photo_to_chat", new_callable=AsyncMock, return_value=mock_resp):
        response = await client.post(
            "/api/request_access",
            json={"image_id": image.id, "search_text_content": "some text"},
            headers=auth_header(user),
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_request_access_image_not_found(client, db_session):
    user = await create_user(db_session)
    response = await client.post(
        "/api/request_access",
        json={"image_id": 999, "search_text_content": "test"},
        headers=auth_header(user),
    )
    assert response.status_code == 404


async def test_handle_access_approve(client, db_session):
    user = await create_user(db_session, email="u@example.com")
    image = await create_image_record(db_session)

    payload = {
        "update_id": 1,
        "callback_query": {
            "id": "q1",
            "from": {"id": 123, "first_name": "Admin", "username": "adm"},
            "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}, "caption": "cap"},
            "data": f"approve:{image.id}:{user.email}",
        },
    }

    with patch("app.routers.telegram.answer_callback_query", new_callable=AsyncMock), \
         patch("app.routers.telegram.edit_message_caption", new_callable=AsyncMock):
        response = await client.post("/api/admin/access", json=payload)

    assert response.status_code == 200
    result = await db_session.execute(
        select(ImagePurchase).where(
            ImagePurchase.user_id == user.id,
            ImagePurchase.image_id == image.id,
        )
    )
    assert result.scalars().first() is not None


async def test_handle_access_deny(client, db_session):
    user = await create_user(db_session, email="u@example.com")
    image = await create_image_record(db_session)

    payload = {
        "update_id": 2,
        "callback_query": {
            "id": "q2",
            "from": {"id": 123, "first_name": "Admin", "username": "adm"},
            "message": {"message_id": 2, "chat": {"id": 1, "type": "private"}, "caption": "cap"},
            "data": f"deny:{image.id}:{user.email}",
        },
    }

    with patch("app.routers.telegram.answer_callback_query", new_callable=AsyncMock), \
         patch("app.routers.telegram.edit_message_caption", new_callable=AsyncMock):
        response = await client.post("/api/admin/access", json=payload)

    assert response.status_code == 200


async def test_handle_access_no_callback(client):
    response = await client.post("/api/admin/access", json={"update_id": 3})
    assert response.status_code == 200
