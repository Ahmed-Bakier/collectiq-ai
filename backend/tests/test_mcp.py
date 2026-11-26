"""MCP server: bearer auth, read + propose only, same guardrails as the in-app agent."""

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import main as main_module
from app import mcp_server
from app.core.config import get_settings
from app.main import create_app
from tests.fakes import make_paypal_client
from tests.paypal_state_fake import FakeInvoiceBook, invoice_json

TODAY = date(2026, 11, 20)
OVERDUE_ID = "INV2-MCPX-0001"
DRAFT_ID = "INV2-MCPX-0002"
TOKEN = "test-mcp-token"


async def _skip_init_db(engine: Any = None) -> None:
    """The test database is created by conftest; never touch the real one."""


@pytest.fixture
def mcp_env(
    monkeypatch: pytest.MonkeyPatch, db_sessionmaker: async_sessionmaker[AsyncSession]
) -> Iterator[TestClient]:
    book = FakeInvoiceBook(
        [
            invoice_json(OVERDUE_ID, "SENT", "2026-11-17", "250.00", "Small Co"),
            invoice_json(DRAFT_ID, "DRAFT", "2026-11-30", "300.00", "Draft Co"),
        ]
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_api_token", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "autopilot_interval_minutes", 0)
    monkeypatch.setattr(mcp_server, "paypal_client_factory", lambda: make_paypal_client(book.handle))
    monkeypatch.setattr(mcp_server, "today_factory", lambda: TODAY)
    monkeypatch.setattr(mcp_server, "sessionmaker_factory", lambda: db_sessionmaker)
    monkeypatch.setattr(main_module, "init_db", _skip_init_db)

    application = create_app()
    # Same per-test database as the shared app (see conftest.py).
    application.dependency_overrides.update(main_module.app.dependency_overrides)
    with TestClient(application) as client:
        yield client


def call(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return client.portal.call(mcp_server.run_tool, name, arguments)


def pending_invoice_ids(client: TestClient) -> list[str]:
    return [action["invoice_id"] for action in client.get("/api/actions?approval_status=pending").json()["items"]]


def test_mcp_requires_a_bearer_token(mcp_env: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert mcp_env.post("/mcp/", json={}).status_code == 401
    assert mcp_env.post("/mcp/", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.setattr(get_settings(), "mcp_api_token", SecretStr(""))
    assert mcp_env.post("/mcp/", json={}, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 503


def test_mcp_proposal_waits_for_human_approval(mcp_env: TestClient) -> None:
    result = call(
        mcp_env,
        "propose_action",
        {"invoice_id": OVERDUE_ID, "action_type": "send_reminder", "reason": "3 days overdue"},
    )

    assert result["accepted"] is True
    assert result["status"] == "awaiting_user_approval"
    assert pending_invoice_ids(mcp_env) == [OVERDUE_ID]
    events = mcp_env.get("/api/audit?limit=100").json()["items"]
    assert any("MCP client" in event["message"] for event in events)


def test_mcp_cannot_bypass_guardrails(mcp_env: TestClient) -> None:
    wrong_action = call(mcp_env, "propose_action", {"invoice_id": DRAFT_ID, "action_type": "send_reminder", "reason": "x"})
    unsafe = call(
        mcp_env,
        "propose_action",
        {
            "invoice_id": OVERDUE_ID,
            "action_type": "send_reminder",
            "reason": "overdue",
            "message_to_client": "Please wire the payment to IBAN DE00 1234.",
        },
    )

    assert wrong_action["accepted"] is False
    assert "not allowed" in wrong_action["error"]
    assert unsafe["accepted"] is False
    assert "payment_redirect" in unsafe["error"]
    assert pending_invoice_ids(mcp_env) == []


def test_mcp_has_no_execute_tool() -> None:
    names = {tool.name for tool in mcp_server.build_mcp_server()._tool_manager.list_tools()}
    assert "propose_action" in names
    assert not any("execute" in name or "approve" in name for name in names)
