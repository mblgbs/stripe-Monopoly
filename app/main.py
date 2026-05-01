from __future__ import annotations

import logging
from typing import Annotated, Any

import httpx
import stripe
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Stripe Monopoly API")


class PaymentLinkCreateRequest(BaseModel):
    app: str | None = None
    context: str | None = None
    reference_id: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, Any] | None = None
    amount_hint_eur: float | None = Field(default=None, ge=0)
    amount_hint_cents: int | None = Field(default=None, ge=0)


def _stripe_settings_dep() -> Settings:
    return get_settings()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stripe-monopoly"}


@app.post("/checkout/session")
def create_checkout_session(
    settings: Annotated[Settings, Depends(_stripe_settings_dep)],
) -> dict[str, str]:
    stripe.api_key = settings.stripe_secret_key
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price": settings.stripe_price_id,
                    "quantity": 1,
                }
            ],
            success_url=settings.checkout_success_url,
            cancel_url=settings.checkout_cancel_url,
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe Checkout Session create failed")
        msg = getattr(exc, "user_message", None) or str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=msg,
        ) from exc

    if not session.url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Session Stripe sans URL de redirection",
        )
    return {"url": session.url}


def _resolve_amount_cents(payload: PaymentLinkCreateRequest | None) -> int | None:
    if payload is None:
        return None
    if payload.amount_hint_cents is not None and payload.amount_hint_cents > 0:
        return int(payload.amount_hint_cents)
    if payload.amount_hint_eur is not None and payload.amount_hint_eur > 0:
        return int(round(payload.amount_hint_eur * 100))
    return None


def _build_line_items(payload: PaymentLinkCreateRequest | None, settings: Settings) -> list[dict[str, Any]]:
    amount_cents = _resolve_amount_cents(payload)
    if amount_cents is None:
        return [{"price": settings.stripe_price_id, "quantity": 1}]

    label_parts = ["Monopoly"]
    if payload and payload.app:
        label_parts.append(payload.app.replace("_", " "))
    if payload and payload.context:
        label_parts.append(payload.context.replace("_", " "))
    if payload and payload.reference_id:
        label_parts.append(payload.reference_id)
    label = " - ".join(label_parts)

    return [
        {
            "price_data": {
                "currency": "eur",
                "unit_amount": amount_cents,
                "product_data": {"name": label},
            },
            "quantity": 1,
        }
    ]


def _build_metadata(payload: PaymentLinkCreateRequest | None) -> dict[str, str]:
    if payload is None:
        return {}

    metadata: dict[str, str] = {}
    if payload.app:
        metadata["app"] = payload.app
    if payload.context:
        metadata["context"] = payload.context
    if payload.reference_id:
        metadata["reference_id"] = payload.reference_id

    if payload.amount_hint_cents is not None:
        metadata["amount_cents"] = str(payload.amount_hint_cents)
    elif payload.amount_hint_eur is not None:
        metadata["amount_cents"] = str(int(round(payload.amount_hint_eur * 100)))

    for key, value in (payload.metadata or {}).items():
        metadata[str(key)] = str(value)
    return metadata


@app.post("/payment-links")
def create_payment_link(
    settings: Annotated[Settings, Depends(_stripe_settings_dep)],
    payload: PaymentLinkCreateRequest | None = Body(default=None),
) -> dict[str, str]:
    stripe.api_key = settings.stripe_secret_key

    create_args: dict[str, Any] = {
        "line_items": _build_line_items(payload, settings),
        "after_completion": {
            "type": "redirect",
            "redirect": {"url": settings.checkout_success_url},
        },
    }

    metadata = _build_metadata(payload)
    if metadata:
        create_args["metadata"] = metadata

    try:
        link = stripe.PaymentLink.create(**create_args)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe PaymentLink create failed")
        msg = getattr(exc, "user_message", None) or str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=msg,
        ) from exc

    if not link.url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment Link Stripe sans URL",
        )
    return {"url": link.url}


def _normalize_wallet_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("type") != "checkout.session.completed":
        return None

    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None

    app_name = str(metadata.get("app", ""))
    context = str(metadata.get("context", ""))
    if app_name != "wallet" or context != "topup":
        return None

    reference_id = str(metadata.get("reference_id", "")).strip()
    if not reference_id:
        return None

    amount_total = obj.get("amount_total")
    amount_cents: int | None = None
    if isinstance(amount_total, int):
        amount_cents = amount_total
    elif isinstance(amount_total, float):
        amount_cents = int(amount_total)
    else:
        raw = str(metadata.get("amount_cents", "")).strip()
        if raw.isdigit():
            amount_cents = int(raw)

    if amount_cents is None or amount_cents <= 0:
        return None

    event_id = str(event.get("id") or obj.get("id") or "").strip()
    if not event_id:
        return None

    payment_status = str(obj.get("payment_status") or "unknown")
    currency = str(obj.get("currency") or "eur")

    return {
        "event_id": event_id,
        "event_type": "checkout.session.completed",
        "payment_status": payment_status,
        "reference_id": reference_id,
        "amount_cents": amount_cents,
        "currency": currency,
    }


def _forward_wallet_webhook(settings: Settings, payload: dict[str, Any]) -> None:
    if not settings.wallet_api_base_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Wallet API base URL is not configured",
        )

    url = f"{settings.wallet_api_base_url}/wallet/webhooks/stripe"
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"X-Wallet-Webhook-Secret": settings.wallet_webhook_shared_secret},
            timeout=settings.webhook_forward_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to forward webhook to wallet-api",
        ) from exc

    if response.status_code >= 400:
        detail = "wallet-api rejected webhook"
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("error") or detail)
        except ValueError:
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


@app.post("/webhook")
async def stripe_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(_stripe_settings_dep)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> JSONResponse:
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En-tete Stripe-Signature manquant",
        )

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corps de requete invalide",
        ) from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signature webhook invalide",
        ) from exc

    normalized = _normalize_wallet_event(event)
    if normalized is not None:
        logger.info(
            "forwarding_wallet_webhook event_id=%s reference_id=%s amount_cents=%s",
            normalized["event_id"],
            normalized["reference_id"],
            normalized["amount_cents"],
        )
        _forward_wallet_webhook(settings, normalized)
    elif event.get("type") == "checkout.session.completed":
        obj = event.get("data", {}).get("object", {})
        logger.info(
            "checkout.session.completed session_id=%s payment_status=%s",
            obj.get("id"),
            obj.get("payment_status"),
        )

    return JSONResponse(content={"received": True})
