from tests.conftest import create_user, create_image_record, auth_header


async def test_get_image_anonymous(client, db_session):
    image = await create_image_record(db_session)
    response = await client.get(f"/api/images/{image.id}")
    assert response.status_code == 403


async def test_get_image_unverified(client, db_session):
    user = await create_user(db_session, is_verified=False)
    image = await create_image_record(db_session)
    response = await client.get(f"/api/images/{image.id}", headers=auth_header(user))
    assert response.status_code == 403


async def test_get_image_verified_user(client, db_session):
    user = await create_user(db_session)
    image = await create_image_record(db_session)
    response = await client.get(f"/api/images/{image.id}", headers=auth_header(user))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "ETag" in response.headers


async def test_get_image_not_found(client, db_session):
    user = await create_user(db_session)
    response = await client.get("/api/images/999", headers=auth_header(user))
    assert response.status_code == 404


async def test_get_image_admin(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image = await create_image_record(db_session)
    response = await client.get(f"/api/images/{image.id}", headers=auth_header(admin))
    assert response.status_code == 200


async def test_get_thumbnail(client, db_session):
    image = await create_image_record(db_session)
    response = await client.get(f"/api/images/{image.id}/thumbnail")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


async def test_get_thumbnail_not_found(client):
    response = await client.get("/api/images/999/thumbnail")
    assert response.status_code == 404


async def test_etag_304(client, db_session):
    user = await create_user(db_session)
    image = await create_image_record(db_session)
    r1 = await client.get(f"/api/images/{image.id}", headers=auth_header(user))
    assert r1.status_code == 200
    etag = r1.headers["ETag"]

    headers = {**auth_header(user), "If-None-Match": etag}
    r2 = await client.get(f"/api/images/{image.id}", headers=headers)
    assert r2.status_code == 304
