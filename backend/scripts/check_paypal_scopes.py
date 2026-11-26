"""Diagnose PayPal Sandbox credentials: prints granted scopes, never the token.

Usage (from backend/): python scripts/check_paypal_scopes.py
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    if not settings.paypal_credentials_configured:
        print("PayPal credentials are not configured in backend/.env")
        return

    response = httpx.post(
        f"{settings.paypal_base_url}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.paypal_client_id, settings.paypal_client_secret.get_secret_value()),
        timeout=15,
    )
    print("Token request HTTP status:", response.status_code)
    if response.status_code != 200:
        return

    payload = response.json()
    scopes = payload.get("scope", "").split()
    invoicing = [scope for scope in scopes if "invoicing" in scope]
    print("App ID:", payload.get("app_id"))
    print("Total scopes granted:", len(scopes))
    print("Invoicing scopes:", invoicing or "NONE")


if __name__ == "__main__":
    main()
