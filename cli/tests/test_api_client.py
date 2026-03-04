import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses

from jroots_cli.api_client import ApiClient, _is_retryable, calculate_sha512

API = "http://test:8000"


# --- calculate_sha512 ---


def test_sha512_correct_hash(tmp_path):
    f = tmp_path / "test.bin"
    content = b"hello world"
    f.write_bytes(content)
    assert calculate_sha512(f) == hashlib.sha512(content).hexdigest()


def test_sha512_empty_file(tmp_path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    assert calculate_sha512(f) == hashlib.sha512(b"").hexdigest()


# --- _is_retryable ---


def test_retryable_connection_error():
    assert _is_retryable(requests.ConnectionError()) is True


def test_retryable_timeout():
    assert _is_retryable(requests.Timeout()) is True


def test_retryable_500():
    resp = MagicMock(status_code=500)
    assert _is_retryable(requests.HTTPError(response=resp)) is True


def test_retryable_502():
    resp = MagicMock(status_code=502)
    assert _is_retryable(requests.HTTPError(response=resp)) is True


def test_not_retryable_400():
    resp = MagicMock(status_code=400)
    assert _is_retryable(requests.HTTPError(response=resp)) is False


def test_not_retryable_404():
    resp = MagicMock(status_code=404)
    assert _is_retryable(requests.HTTPError(response=resp)) is False


def test_not_retryable_unrelated_exception():
    assert _is_retryable(ValueError("nope")) is False


# --- ApiClient.upload_image ---


@responses.activate
def test_upload_image_sends_correct_request(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8test")
    responses.add(
        responses.POST, f"{API}/api/admin/images", json={"id": 1}, status=200
    )

    client = ApiClient(requests.Session(), API)
    resp = client.upload_image(
        path=img, image_key="key", image_source_id="1",
        image_path="test/path", sha512="abc123",
    )
    assert resp.status_code == 200
    assert len(responses.calls) == 1
    body = responses.calls[0].request.body
    assert b"abc123" in body
    assert b"key" in body


# --- ApiClient.upload_object ---


@responses.activate
def test_upload_object_sends_correct_request():
    responses.add(
        responses.POST, f"{API}/api/admin/objects", json={"id": 1}, status=200
    )

    client = ApiClient(requests.Session(), API)
    resp = client.upload_object(sha512="abc", text_content="Test Name", price="5000")
    assert resp.status_code == 200
    body = responses.calls[0].request.body
    assert "abc" in body
    assert "Test+Name" in body or "Test%20Name" in body or "Test Name" in body


# --- ApiClient.login ---


@responses.activate
def test_login_returns_token():
    responses.add(
        responses.POST, f"{API}/api/login",
        json={"access_token": "tok123"}, status=200,
    )

    client = ApiClient(requests.Session(), API)
    result = client.login("admin", "pass")
    assert result == {"access_token": "tok123"}


@responses.activate
def test_login_raises_on_401():
    responses.add(
        responses.POST, f"{API}/api/login",
        json={"detail": "Invalid"}, status=401,
    )

    client = ApiClient(requests.Session(), API)
    with pytest.raises(requests.HTTPError):
        client.login("admin", "wrong")


# --- ApiClient.ping ---


@responses.activate
def test_ping_returns_true_on_success():
    responses.add(responses.GET, f"{API}/", status=200)
    client = ApiClient(requests.Session(), API)
    assert client.ping() is True


@responses.activate
def test_ping_returns_true_even_on_404():
    responses.add(responses.GET, f"{API}/", status=404)
    client = ApiClient(requests.Session(), API)
    assert client.ping() is True


@responses.activate
def test_ping_returns_false_on_connection_error():
    responses.add(responses.GET, f"{API}/", body=requests.ConnectionError())
    client = ApiClient(requests.Session(), API)
    assert client.ping() is False


# --- Retry behaviour ---


@responses.activate
def test_retries_on_500_then_succeeds(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8test")

    responses.add(responses.POST, f"{API}/api/admin/images", status=500)
    responses.add(responses.POST, f"{API}/api/admin/images", json={"id": 1}, status=200)

    client = ApiClient(requests.Session(), API)
    with patch("time.sleep"):
        resp = client.upload_image(
            path=img, image_key="k", image_source_id="1",
            image_path="p", sha512="abc",
        )
    assert resp.status_code == 200
    assert len(responses.calls) == 2


@responses.activate
def test_does_not_retry_on_400(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8test")

    responses.add(
        responses.POST, f"{API}/api/admin/images",
        json={"detail": "bad"}, status=400,
    )

    client = ApiClient(requests.Session(), API)
    with pytest.raises(requests.HTTPError) as exc_info:
        client.upload_image(
            path=img, image_key="k", image_source_id="1",
            image_path="p", sha512="abc",
        )
    assert exc_info.value.response.status_code == 400
    assert len(responses.calls) == 1


@responses.activate
def test_retry_exhausted_raises(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8test")

    for _ in range(3):
        responses.add(responses.POST, f"{API}/api/admin/images", status=500)

    client = ApiClient(requests.Session(), API)
    with patch("time.sleep"):
        with pytest.raises(requests.HTTPError) as exc_info:
            client.upload_image(
                path=img, image_key="k", image_source_id="1",
                image_path="p", sha512="abc",
            )
    assert exc_info.value.response.status_code == 500
    assert len(responses.calls) == 3
