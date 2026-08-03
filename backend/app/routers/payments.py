import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.payments import get_provider
from app.payments.base import ProviderError, SignatureError
from app.payments.handler import UnprocessableEvent, process_payment_event
from app.payments.tariffs import TARIFFS
from app.services.auth import get_current_user

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api", tags=["payments"])


class CheckoutRequest(BaseModel):
    tariff: str
    provider: str = "polar"


@router.post("/payments/checkout")
async def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    tariff = TARIFFS.get(data.tariff)
    if tariff is None:
        raise HTTPException(status_code=400, detail=f"Unknown tariff: {data.tariff!r}")
    provider = get_provider(data.provider)
    if provider is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown payment provider: {data.provider!r}",
        )
    # Only the Polar rail supports recurring billing; the NOWPayments invoice
    # and YuKassa redirect flows are one-off payments.
    if tariff.kind == "subscription" and data.provider != "polar":
        raise HTTPException(
            status_code=400,
            detail="Subscription tariff is only available via Polar",
        )
    settings = get_settings()
    success_url = f"{settings.frontend_url}/billing/success"
    cancel_url = f"{settings.frontend_url}/billing/cancel"
    try:
        return await provider.create_checkout(
            user=current_user,
            tariff=tariff,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ProviderError as exc:
        logger.error("Checkout creation failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Payment provider unavailable"
        ) from exc


@router.post("/webhooks/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Server-to-server payment webhook endpoint.

    No auth/CSRF (authenticity is proven by the provider signature or IP
    allowlist + re-verification) and no slowapi rate limit. Always 200 after
    successful processing (including duplicates), 401 on failed verification,
    400 on malformed/unprocessable payloads.
    """
    prov = get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="Unknown payment provider")
    raw_body = await request.body()
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip and request.client:
        client_ip = request.client.host
    try:
        event = await prov.verify_and_parse(
            request.headers, raw_body, client_ip=client_ip or None
        )
    except SignatureError as exc:
        logger.warning("Webhook %s rejected: %s", provider, exc)
        raise HTTPException(
            status_code=401, detail="Webhook verification failed"
        ) from exc
    except ValueError as exc:
        logger.warning("Webhook %s malformed: %s", provider, exc)
        raise HTTPException(
            status_code=400, detail="Malformed webhook payload"
        ) from exc
    try:
        result = await process_payment_event(db, event)
    except UnprocessableEvent as exc:
        logger.warning("Webhook %s unprocessable: %s", provider, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}
