from __future__ import annotations

import logging
from typing import Annotated

import stripe
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Stripe Monopoly API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stripe-monopoly"}


def _stripe_settings_dep() -> Settings:
    return get_settings()


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


@app.post("/payment-links")
def create_payment_link(
    settings: Annotated[Settings, Depends(_stripe_settings_dep)],
) -> dict[str, str]:
    stripe.api_key = settings.stripe_secret_key
    try:
        link = stripe.PaymentLink.create(
            line_items=[
                {
                    "price": settings.stripe_price_id,
                    "quantity": 1,
                }
            ],
            after_completion={
                "type": "redirect",
                "redirect": {"url": settings.checkout_success_url},
            },
        )
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


@app.post("/webhook")
async def stripe_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(_stripe_settings_dep)],
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> JSONResponse:
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En-tête Stripe-Signature manquant",
        )

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corps de requête invalide",
        ) from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signature webhook invalide",
        ) from exc

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        logger.info(
            "checkout.session.completed session_id=%s payment_status=%s",
            obj.get("id"),
            obj.get("payment_status"),
        )

    return JSONResponse(content={"received": True})
