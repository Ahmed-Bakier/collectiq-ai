"""PayPal webhook signature verification (PayPal's postback method)."""

from collections.abc import Mapping
from typing import Any

from app.integrations.paypal.client import PayPalClient

VERIFY_PATH = "/v1/notifications/verify-webhook-signature"

# Request field -> PayPal webhook header.
SIGNATURE_HEADERS: dict[str, str] = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


async def verify_webhook_signature(
    client: PayPalClient,
    headers: Mapping[str, str],
    event: dict[str, Any],
    webhook_id: str,
) -> bool:
    """Ask PayPal whether this event was really signed by PayPal for our webhook."""
    body: dict[str, Any] = {field: headers.get(header) for field, header in SIGNATURE_HEADERS.items()}
    if not all(body.values()):
        return False
    body["webhook_id"] = webhook_id
    body["webhook_event"] = event
    payload = await client.post(VERIFY_PATH, body, f"verify-{body['transmission_id']}"[:100])
    return isinstance(payload, dict) and payload.get("verification_status") == "SUCCESS"
