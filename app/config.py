from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_id: str
    checkout_success_url: str
    checkout_cancel_url: str
    wallet_api_base_url: str
    wallet_webhook_shared_secret: str
    webhook_forward_timeout_seconds: float
    port: int


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante ou vide: {name}")
    return value


def load_settings() -> Settings:
    return Settings(
        stripe_secret_key=_require("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=_require("STRIPE_WEBHOOK_SECRET"),
        stripe_price_id=_require("STRIPE_PRICE_ID"),
        checkout_success_url=_require("CHECKOUT_SUCCESS_URL"),
        checkout_cancel_url=_require("CHECKOUT_CANCEL_URL"),
        wallet_api_base_url=os.getenv("WALLET_API_BASE_URL", "http://127.0.0.1:8007").strip().rstrip("/"),
        wallet_webhook_shared_secret=os.getenv("WALLET_WEBHOOK_SHARED_SECRET", "wallet-webhook-secret").strip(),
        webhook_forward_timeout_seconds=float(os.getenv("WEBHOOK_FORWARD_TIMEOUT_SECONDS", "5")),
        port=int(os.getenv("PORT", "8006")),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
