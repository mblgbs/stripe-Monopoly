from __future__ import annotations

import pytest

from app.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _stripe_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_fake")
    monkeypatch.setenv("CHECKOUT_SUCCESS_URL", "http://127.0.0.1:8006/checkout/success")
    monkeypatch.setenv("CHECKOUT_CANCEL_URL", "http://127.0.0.1:8006/checkout/cancel")
    monkeypatch.setenv("WALLET_API_BASE_URL", "http://127.0.0.1:8007")
    monkeypatch.setenv("WALLET_WEBHOOK_SHARED_SECRET", "wallet-webhook-secret")
    monkeypatch.setenv("WEBHOOK_FORWARD_TIMEOUT_SECONDS", "2")
    clear_settings_cache()
    yield
    clear_settings_cache()
