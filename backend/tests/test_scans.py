"""Scan pipeline tests: upload validation, vision extraction (mocked),
watermarking, charging, and scan context in chat messages."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image as PILImage
from sqlalchemy import select, func

from app.config import get_settings
from app.models import ChatMessage, Credit, CreditTransaction, Payment, Scan
from app.rate_limit import limiter
from app.services import llm_router, scan_pipeline
from tests.conftest import auth_header, create_user

# --- Fakes and helpers ---


class _FakeVisionCompletions:
    """OpenAI-client double for non-streaming vision calls."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        script = self._scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=script))]
        )


class _FakeVisionClient:
    def __init__(self, scripts):
        self.chat = SimpleNamespace(completions=_FakeVisionCompletions(scripts))


@pytest.fixture
def fake_vision(monkeypatch):
    """Install a scripted vision client; returns the completions recorder."""

    def install(scripts):
        client = _FakeVisionClient(scripts)
        monkeypatch.setattr(llm_router, "_client", client)
        return client.chat.completions

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    limiter.reset()  # scans POST is capped at 5/min per IP across the suite


GOOD_VISION_JSON = json.dumps(
    {
        "transcription": "Состоялось бракосочетание: Шлема Кацнельсон...",
        "doc_type": "метрическая запись о браке",
        "names": ["Шлема Кацнельсон", "Хая Рабинович"],
        "dates": ["1850"],
        "place": "Клинцы",
        "confidence": "high",
    }
)


def make_image_bytes(fmt="JPEG", width=300, height=200, color="blue"):
    img = PILImage.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


async def create_user_with_scans(db, *, email, scans=2, paid=False):
    user = await create_user(db, email=email)
    db.add(Credit(user_id=user.id, searches_left=5, scans_left=scans))
    if paid:
        db.add(
            Payment(
                provider="stripe",
                provider_payment_id=f"pay-{email}",
                user_id=user.id,
                status="succeeded",
            )
        )
    await db.commit()
    return user


async def create_chat_session(client, user):
    response = await client.post("/api/chat/sessions", headers=auth_header(user))
    assert response.status_code == 201
    return response.json()["id"]


async def upload_scan(client, user, session_id, data, filename="scan.jpg"):
    return await client.post(
        f"/api/chat/sessions/{session_id}/scans",
        files={"file": (filename, data)},
        headers=auth_header(user),
    )


async def scans_left(db, user_id):
    result = await db.execute(
        select(Credit.scans_left).where(Credit.user_id == user_id)
    )
    return result.scalar_one()


# --- Validation ---


async def test_upload_too_large_returns_413(client, db_session, fake_vision):
    vision = fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(db_session, email="scan-big@example.com")
    session_id = await create_chat_session(client, user)

    data = b"\xff\xd8\xff" + b"\0" * (scan_pipeline.MAX_SCAN_BYTES + 1)
    response = await upload_scan(client, user, session_id, data)

    assert response.status_code == 413
    assert vision.calls == []  # validation happens before vision


async def test_upload_non_image_magic_bytes_returns_415(
    client, db_session, fake_vision
):
    vision = fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(db_session, email="scan-exe@example.com")
    session_id = await create_chat_session(client, user)

    # A PE executable renamed to .jpg — extension is never trusted.
    data = b"MZ\x90\x00" + b"\x00" * 512
    response = await upload_scan(client, user, session_id, data, filename="scan.jpg")

    assert response.status_code == 415
    assert vision.calls == []


async def test_upload_tiff_accepted_and_converted(client, db_session, fake_vision):
    fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(db_session, email="scan-tiff@example.com")
    session_id = await create_chat_session(client, user)

    response = await upload_scan(
        client, user, session_id, make_image_bytes(fmt="TIFF"), filename="scan.tiff"
    )

    assert response.status_code == 201
    scan = await db_session.get(Scan, response.json()["scan_id"])
    with PILImage.open(scan.file_path) as stored:
        assert stored.format == "JPEG"


# --- Successful cycle ---


async def test_upload_success_free_user_watermarked(client, db_session, fake_vision):
    vision = fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(
        db_session, email="scan-free@example.com", scans=1
    )
    session_id = await create_chat_session(client, user)

    response = await upload_scan(
        client, user, session_id, make_image_bytes(width=3000, height=2400)
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["extracted_text"] == "Состоялось бракосочетание: Шлема Кацнельсон..."
    assert payload["metadata"] == {
        "doc_type": "метрическая запись о браке",
        "names": ["Шлема Кацнельсон", "Хая Рабинович"],
        "dates": ["1850"],
        "place": "Клинцы",
    }
    assert payload["model_used"] == get_settings().llm_model_main
    assert payload["watermarked"] is True

    scan = await db_session.get(Scan, payload["scan_id"])
    assert scan.status == "done"
    assert scan.session_id == session_id
    assert scan.watermarked is True
    with PILImage.open(scan.file_path) as stored:
        assert max(stored.size) <= scan_pipeline.MAX_SCAN_DIMENSION

    # Exactly one scan charged, journaled against the scan id.
    assert await scans_left(db_session, user.id) == 0
    tx = (
        await db_session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.reason == "usage",
            )
        )
    ).scalar_one()
    assert tx.delta_scans == -1
    assert tx.ref_id == f"scan:{scan.id}"

    assert len(vision.calls) == 1
    assert vision.calls[0]["model"] == get_settings().llm_model_main


async def test_upload_success_paid_user_not_watermarked(
    client, db_session, fake_vision
):
    fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(
        db_session, email="scan-paid@example.com", scans=2, paid=True
    )
    session_id = await create_chat_session(client, user)

    response = await upload_scan(
        client, user, session_id, make_image_bytes(width=3000, height=2400)
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["watermarked"] is False

    scan = await db_session.get(Scan, payload["scan_id"])
    assert scan.watermarked is False
    with PILImage.open(scan.file_path) as stored:
        # Paid copies are stored unmodified apart from the 2000px downscale.
        assert max(stored.size) == scan_pipeline.MAX_SCAN_DIMENSION
    assert await scans_left(db_session, user.id) == 1


async def test_scan_image_endpoint_owner_only(client, db_session, fake_vision):
    fake_vision([GOOD_VISION_JSON])
    owner = await create_user_with_scans(db_session, email="scan-img@example.com")
    other = await create_user_with_scans(db_session, email="scan-img2@example.com")
    session_id = await create_chat_session(client, owner)
    scan_id = (await upload_scan(client, owner, session_id, make_image_bytes())).json()[
        "scan_id"
    ]

    response = await client.get(
        f"/api/chat/scans/{scan_id}/image", headers=auth_header(owner)
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"

    response = await client.get(
        f"/api/chat/scans/{scan_id}/image", headers=auth_header(other)
    )
    assert response.status_code == 404

    response = await client.get(
        "/api/chat/scans/99999/image", headers=auth_header(owner)
    )
    assert response.status_code == 404


async def test_upload_foreign_session_is_404(client, db_session, fake_vision):
    fake_vision([GOOD_VISION_JSON])
    owner = await create_user_with_scans(db_session, email="scan-sess@example.com")
    other = await create_user_with_scans(db_session, email="scan-sess2@example.com")
    session_id = await create_chat_session(client, owner)

    response = await upload_scan(client, other, session_id, make_image_bytes())
    assert response.status_code == 404


# --- Credits ---


async def test_no_scans_left_returns_402_before_vision(client, db_session, fake_vision):
    vision = fake_vision([GOOD_VISION_JSON])
    user = await create_user_with_scans(
        db_session, email="scan-broke@example.com", scans=0
    )
    session_id = await create_chat_session(client, user)

    response = await upload_scan(client, user, session_id, make_image_bytes())

    assert response.status_code == 402
    assert response.json() == {"detail": "no_scans_left"}
    assert vision.calls == []  # no free vision burns without credits
    count = (await db_session.execute(select(func.count(Scan.id)))).scalar_one()
    assert count == 0


async def test_vision_failure_status_error_and_not_charged(
    client, db_session, fake_vision
):
    vision = fake_vision([RuntimeError("moonshot down"), RuntimeError("still down")])
    user = await create_user_with_scans(
        db_session, email="scan-fail@example.com", scans=2
    )
    session_id = await create_chat_session(client, user)

    response = await upload_scan(client, user, session_id, make_image_bytes())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["extracted_text"] is None
    assert await scans_left(db_session, user.id) == 2  # never charged

    scan = await db_session.get(Scan, payload["scan_id"])
    assert scan.status == "error"
    assert len(vision.calls) == 2  # main + escalation both attempted


async def test_unparseable_main_escalates_once(client, db_session, fake_vision):
    vision = fake_vision(["не могу прочитать, извините", GOOD_VISION_JSON])
    user = await create_user_with_scans(db_session, email="scan-esc@example.com")
    session_id = await create_chat_session(client, user)

    response = await upload_scan(client, user, session_id, make_image_bytes())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "done"
    assert payload["model_used"] == get_settings().llm_model_escalation
    assert [call["model"] for call in vision.calls] == [
        get_settings().llm_model_main,
        get_settings().llm_model_escalation,
    ]


async def test_low_confidence_escalates(client, db_session, fake_vision):
    low_confidence = json.dumps(
        {
            "transcription": "[неразборчиво]",
            "doc_type": None,
            "names": [],
            "dates": [],
            "place": None,
            "confidence": "low",
        }
    )
    vision = fake_vision([low_confidence, GOOD_VISION_JSON])
    user = await create_user_with_scans(db_session, email="scan-low@example.com")
    session_id = await create_chat_session(client, user)

    response = await upload_scan(client, user, session_id, make_image_bytes())

    assert response.status_code == 201
    assert response.json()["model_used"] == get_settings().llm_model_escalation
    assert len(vision.calls) == 2


# --- Messages with scan_ids ---


class _FakeStreamCompletions:
    """Streaming completion double that records its kwargs."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)

        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()


@pytest.fixture
def fake_stream_llm(monkeypatch):
    def install(texts=("ответ",), usage=(10, 5)):
        chunks = [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
                usage=None,
            )
            for text in texts
        ]
        chunks.append(
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=usage[0], completion_tokens=usage[1]
                ),
            )
        )
        completions = _FakeStreamCompletions(chunks)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        monkeypatch.setattr(llm_router, "_client", client)
        return completions

    yield install
    monkeypatch.setattr(llm_router, "_client", None)


async def create_done_scan(db, user, session_id, **overrides):
    scan = Scan(
        user_id=user.id,
        session_id=session_id,
        status="done",
        extracted_text="Ревизская сказка 1850 года, Шлема Кацнельсон с семьёй.",
        metadata_json={
            "doc_type": "ревизская сказка",
            "names": ["Шлема Кацнельсон"],
            "dates": ["1850"],
            "place": "Клинцы",
        },
        model_used=get_settings().llm_model_main,
        **overrides,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    return scan


async def test_message_with_scan_ids_injects_context(
    client, db_session, fake_stream_llm
):
    completions = fake_stream_llm()
    user = await create_user_with_scans(db_session, email="scan-msg@example.com")
    session_id = await create_chat_session(client, user)
    scan = await create_done_scan(db_session, user, session_id)

    response = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "Что на этом скане?", "scan_ids": [scan.id]},
        headers=auth_header(user),
    )

    assert response.status_code == 200
    # The server pulled the extracted text from the DB into the LLM context.
    sent_messages = completions.calls[0]["messages"]
    user_message = next(m for m in sent_messages if m["role"] == "user")
    assert "Ревизская сказка 1850 года" in user_message["content"]
    assert f"#{scan.id}" in user_message["content"]
    assert "Шлема Кацнельсон" in user_message["content"]
    # The persisted message keeps the raw user text + the scan reference.
    message = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id, ChatMessage.role == "user"
            )
        )
    ).scalar_one()
    assert message.content == "Что на этом скане?"
    assert message.scan_ids == [scan.id]


async def test_message_with_foreign_scan_id_returns_400(
    client, db_session, fake_stream_llm
):
    fake_stream_llm()
    owner = await create_user_with_scans(db_session, email="scan-own@example.com")
    other = await create_user_with_scans(db_session, email="scan-oth@example.com")
    session_id = await create_chat_session(client, other)
    foreign_scan = await create_done_scan(db_session, owner, None)

    response = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "гляди", "scan_ids": [foreign_scan.id]},
        headers=auth_header(other),
    )

    assert response.status_code == 400
    # Nothing was persisted for the rejected message.
    count = (
        await db_session.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == session_id
            )
        )
    ).scalar_one()
    assert count == 0


async def test_message_with_unknown_scan_id_returns_400(
    client, db_session, fake_stream_llm
):
    fake_stream_llm()
    user = await create_user_with_scans(db_session, email="scan-unk@example.com")
    session_id = await create_chat_session(client, user)

    response = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "гляди", "scan_ids": [424242]},
        headers=auth_header(user),
    )

    assert response.status_code == 400
