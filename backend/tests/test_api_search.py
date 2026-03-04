from tests.conftest import create_user, create_image_record, create_search_obj, auth_header


async def test_search_returns_results(client, db_session):
    image = await create_image_record(db_session, image_path="fond/123", image_key="ABC-123")
    await create_search_obj(db_session, text_content="test document text", price=100, image_id=image.id)

    response = await client.get("/api/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["image"]["image_path"] == "********"


async def test_search_authenticated_without_purchase(client, db_session):
    user = await create_user(db_session)
    image = await create_image_record(db_session)
    await create_search_obj(db_session, text_content="test document", price=50, image_id=image.id)

    response = await client.get("/api/search?q=test", headers=auth_header(user))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["image"]["image_path"] == "********"


async def test_search_no_results(client):
    response = await client.get("/api/search?q=zzzznonexistent99999")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_search_pagination(client, db_session):
    image = await create_image_record(db_session)
    for i in range(5):
        await create_search_obj(db_session, text_content=f"test item {i}", price=10, image_id=image.id)

    response = await client.get("/api/search?q=test&skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
