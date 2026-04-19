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
    clear_settings_cache()
    yield
    clear_settings_cache()
