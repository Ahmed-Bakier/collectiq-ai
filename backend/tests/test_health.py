"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["paypal_environment"] == "sandbox"
    assert isinstance(body["paypal_credentials_configured"], bool)


def test_health_does_not_leak_secrets() -> None:
    body = client.get("/api/health").json()

    assert "paypal_client_secret" not in body
    assert "paypal_client_id" not in body
