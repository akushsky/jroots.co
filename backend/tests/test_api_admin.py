import hashlib

from app.models import ImageSource
from tests.conftest import (
    create_user, create_image_record, create_search_obj,
    make_test_image_bytes, auth_header,
)


async def test_create_object_unauthorized(client):
    response = await client.post("/api/admin/objects")
    assert response.status_code == 401


async def test_create_image_success(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image_bytes = make_test_image_bytes()
    sha512 = hashlib.sha512(image_bytes).hexdigest()

    response = await client.post(
        "/api/admin/images",
        data={"image_path": "fond/001", "image_key": "KEY-001", "image_file_sha512": sha512},
        files={"image_file": ("test.jpg", image_bytes, "image/jpeg")},
        headers=auth_header(admin),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["image_path"] == "fond/001"
    assert data["image_key"] == "KEY-001"


async def test_create_object_success(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image_bytes = make_test_image_bytes()
    sha512 = hashlib.sha512(image_bytes).hexdigest()

    response = await client.post(
        "/api/admin/objects",
        data={
            "text_content": "Test content", "price": 50,
            "image_path": "fond/002", "image_key": "KEY-002",
            "image_file_sha512": sha512,
        },
        files={"image_file": ("test.jpg", image_bytes, "image/jpeg")},
        headers=auth_header(admin),
    )
    assert response.status_code == 200
    assert response.json()["text_content"] == "Test content"


async def test_list_objects(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image = await create_image_record(db_session)
    await create_search_obj(db_session, text_content="Obj 1", price=10, image_id=image.id)
    await create_search_obj(db_session, text_content="Obj 2", price=20, image_id=image.id)

    response = await client.get("/api/admin/objects", headers=auth_header(admin))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_update_object(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image = await create_image_record(db_session)
    obj = await create_search_obj(db_session, text_content="Original", price=10, image_id=image.id)

    response = await client.put(
        f"/api/admin/objects/{obj.id}",
        data={
            "text_content": "Updated", "price": 25,
            "image_path": image.image_path, "image_key": image.image_key,
        },
        headers=auth_header(admin),
    )
    assert response.status_code == 200
    assert response.json()["text_content"] == "Updated"


async def test_delete_object(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    image = await create_image_record(db_session)
    obj = await create_search_obj(db_session, text_content="Delete me", price=5, image_id=image.id)

    response = await client.delete(f"/api/admin/objects/{obj.id}", headers=auth_header(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"


async def test_delete_object_not_found(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    response = await client.delete("/api/admin/objects/999", headers=auth_header(admin))
    assert response.status_code == 404


async def test_list_image_sources(client, db_session):
    admin = await create_user(db_session, username="admin", email="admin@test.com", is_admin=True)
    source = ImageSource(source_name="Test Archive", description="A test source")
    db_session.add(source)
    await db_session.commit()

    response = await client.get("/api/admin/image-sources", headers=auth_header(admin))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source_name"] == "Test Archive"
