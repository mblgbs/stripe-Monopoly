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
    import stripe

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


def test_payment_link_accepts_amount_and_metadata(client: TestClient) -> None:
    mock_link = MagicMock()
    mock_link.url = "https://buy.stripe.com/test_pl_amount"

    with patch("app.main.stripe.PaymentLink.create", return_value=mock_link) as mocked_create:
        r = client.post(
            "/payment-links",
            json={
                "app": "wallet",
                "context": "topup",
                "reference_id": "wallet-topup-001",
                "amount_hint_cents": 2599,
                "metadata": {"wallet_id": "WAL1234ABCD"},
            },
        )

    assert r.status_code == 200
    assert r.json() == {"url": "https://buy.stripe.com/test_pl_amount"}
    kwargs = mocked_create.call_args.kwargs
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 2599
    assert kwargs["line_items"][0]["price_data"]["product_data"]["name"] == (
        "Monopoly - wallet - topup - wallet-topup-001"
    )
    assert kwargs["metadata"]["app"] == "wallet"
    assert kwargs["metadata"]["context"] == "topup"
    assert kwargs["metadata"]["reference_id"] == "wallet-topup-001"
    assert kwargs["metadata"]["wallet_id"] == "WAL1234ABCD"


def test_payment_link_stripe_error(client: TestClient) -> None:
    import stripe

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


def test_webhook_wallet_topup_forwarded(client: TestClient) -> None:
    event = {
        "id": "evt_wallet_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_wallet_1",
                "payment_status": "paid",
                "amount_total": 3400,
                "currency": "eur",
                "metadata": {
                    "app": "wallet",
                    "context": "topup",
                    "reference_id": "wallet-topup-1",
                    "wallet_id": "WAL11AA22BB",
                },
            }
        },
    }
    forward_response = MagicMock()
    forward_response.status_code = 200
    forward_response.json.return_value = {"received": True, "processed": True}

    with patch("app.main.stripe.Webhook.construct_event", return_value=event):
        with patch("app.main.httpx.post", return_value=forward_response) as mocked_post:
            r = client.post(
                "/webhook",
                content=b'{"x":1}',
                headers={"Stripe-Signature": "t=1,v1=fake"},
            )

    assert r.status_code == 200
    body = mocked_post.call_args.kwargs["json"]
    assert body["event_id"] == "evt_wallet_1"
    assert body["reference_id"] == "wallet-topup-1"
    assert body["amount_cents"] == 3400


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
    import stripe

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
