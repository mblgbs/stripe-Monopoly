from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "stripe-monopoly"}


def test_checkout_session_returns_url(client: TestClient) -> None:
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_123"

    with patch("app.main.stripe.checkout.Session.create", return_value=mock_session):
        r = client.post("/checkout/session")

    assert r.status_code == 200
    assert r.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_123"}


def test_checkout_session_stripe_error(client: TestClient) -> None:
    import stripe.error

    with patch(
        "app.main.stripe.checkout.Session.create",
        side_effect=stripe.error.StripeError("boom"),
    ):
        r = client.post("/checkout/session")
    assert r.status_code == 502


def test_payment_link_returns_url(client: TestClient) -> None:
    mock_link = MagicMock()
    mock_link.url = "https://buy.stripe.com/test_pl_123"

    with patch("app.main.stripe.PaymentLink.create", return_value=mock_link):
        r = client.post("/payment-links")

    assert r.status_code == 200
    assert r.json() == {"url": "https://buy.stripe.com/test_pl_123"}


def test_payment_link_stripe_error(client: TestClient) -> None:
    import stripe.error

    with patch(
        "app.main.stripe.PaymentLink.create",
        side_effect=stripe.error.StripeError("boom"),
    ):
        r = client.post("/payment-links")
    assert r.status_code == 502


def test_webhook_requires_signature(client: TestClient) -> None:
    r = client.post("/webhook", content=b"{}")
    assert r.status_code == 400


def test_webhook_checkout_completed(client: TestClient) -> None:
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_abc",
                "payment_status": "paid",
            }
        },
    }
    with patch("app.main.stripe.Webhook.construct_event", return_value=event):
        r = client.post(
            "/webhook",
            content=b'{"x":1}',
            headers={"Stripe-Signature": "t=1,v1=fake"},
        )
    assert r.status_code == 200
    assert r.json() == {"received": True}


def test_webhook_invalid_payload(client: TestClient) -> None:
    with patch(
        "app.main.stripe.Webhook.construct_event",
        side_effect=ValueError("bad payload"),
    ):
        r = client.post(
            "/webhook",
            content=b"not-json",
            headers={"Stripe-Signature": "t=1,v1=x"},
        )
    assert r.status_code == 400


def test_webhook_invalid_signature(client: TestClient) -> None:
    import stripe.error

    with patch(
        "app.main.stripe.Webhook.construct_event",
        side_effect=stripe.error.SignatureVerificationError("bad", "sig"),
    ):
        r = client.post(
            "/webhook",
            content=b"{}",
            headers={"Stripe-Signature": "t=1,v1=x"},
        )
    assert r.status_code == 400
