"""Unit tests for the deterministic invoice analysis rules."""

from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.analysis import CollectionState, PriorityLevel, SuggestedAction
from app.schemas.invoices import InvoiceSummary
from app.services.invoice_analysis import analyze_invoice, analyze_invoices

TODAY = date(2026, 11, 9)


def make_invoice(**overrides: Any) -> InvoiceSummary:
    values: dict[str, Any] = {
        "id": "INV2-TEST-0001",
        "status": "SENT",
        "currency_code": "USD",
        "total_amount": Decimal("100.00"),
        "amount_due": Decimal("100.00"),
        "due_date": TODAY,
    }
    values.update(overrides)
    return InvoiceSummary(**values)


def test_overdue_invoice_has_days_overdue_and_reminder_action() -> None:
    result = analyze_invoice(make_invoice(due_date=date(2026, 11, 5)), TODAY)

    assert result.collection_state is CollectionState.OVERDUE
    assert result.days_overdue == 4
    assert result.days_until_due is None
    assert result.suggested_action is SuggestedAction.SEND_REMINDER
    assert "passed 4 days ago" in result.reasons[1]


def test_due_today() -> None:
    result = analyze_invoice(make_invoice(due_date=TODAY), TODAY)
    assert result.collection_state is CollectionState.DUE_TODAY
    assert result.suggested_action is SuggestedAction.SEND_REMINDER


def test_due_soon_window_boundary() -> None:
    inside = analyze_invoice(make_invoice(due_date=date(2026, 11, 12)), TODAY)   # 3 days
    outside = analyze_invoice(make_invoice(due_date=date(2026, 11, 13)), TODAY)  # 4 days

    assert inside.collection_state is CollectionState.DUE_SOON
    assert inside.suggested_action is SuggestedAction.MONITOR
    assert outside.collection_state is CollectionState.NOT_DUE
    assert outside.suggested_action is SuggestedAction.NONE


def test_unpaid_partially_paid_and_shared_are_collectible() -> None:
    for status in ("UNPAID", "PARTIALLY_PAID", "SHARED"):
        result = analyze_invoice(make_invoice(status=status, due_date=date(2026, 11, 1)), TODAY)
        assert result.collection_state is CollectionState.OVERDUE, status


def test_draft_suggests_sending() -> None:
    result = analyze_invoice(make_invoice(status="DRAFT", due_date=date(2026, 11, 1)), TODAY)
    assert result.collection_state is CollectionState.DRAFT
    assert result.suggested_action is SuggestedAction.SEND_INVOICE


def test_paid_invoice_is_closed_even_if_due_date_passed() -> None:
    result = analyze_invoice(make_invoice(status="PAID", due_date=date(2026, 10, 1)), TODAY)

    assert result.collection_state is CollectionState.CLOSED
    assert result.priority_score == 0
    assert result.priority_level is PriorityLevel.NONE
    assert result.suggested_action is SuggestedAction.NONE


def test_missing_due_date_is_never_marked_overdue() -> None:
    result = analyze_invoice(make_invoice(due_date=None), TODAY)

    assert result.collection_state is CollectionState.NO_DUE_DATE
    assert result.days_overdue is None
    assert result.suggested_action is SuggestedAction.REVIEW


def test_unknown_status_requires_review() -> None:
    result = analyze_invoice(make_invoice(status="SOMETHING_NEW"), TODAY)
    assert result.collection_state is CollectionState.UNKNOWN
    assert result.suggested_action is SuggestedAction.REVIEW


def test_amount_due_is_preferred_over_total() -> None:
    result = analyze_invoice(
        make_invoice(status="PARTIALLY_PAID", total_amount=Decimal("1000.00"), amount_due=Decimal("100.00")),
        TODAY,
    )
    assert "Amount owed: 100.00 USD" in result.reasons


def test_older_and_larger_overdue_invoices_rank_higher() -> None:
    small_recent = analyze_invoice(
        make_invoice(due_date=date(2026, 11, 8), amount_due=Decimal("100.00")), TODAY
    )
    large_old = analyze_invoice(
        make_invoice(due_date=date(2026, 11, 1), amount_due=Decimal("2000.00")), TODAY
    )

    assert large_old.priority_score > small_recent.priority_score
    assert large_old.priority_level is PriorityLevel.HIGH


def test_portfolio_summary_and_sorting() -> None:
    invoices = [
        make_invoice(id="INV2-A", due_date=date(2026, 11, 20), amount_due=Decimal("2350.00")),
        make_invoice(id="INV2-B", due_date=date(2026, 11, 5), amount_due=Decimal("1200.00")),
        make_invoice(id="INV2-C", status="DRAFT", due_date=date(2026, 11, 11), amount_due=Decimal("300.00")),
        make_invoice(id="INV2-D", status="PAID", amount_due=Decimal("0.00")),
    ]

    report = analyze_invoices(invoices, today=TODAY, timezone="America/Los_Angeles")

    assert [item.invoice.id for item in report.invoices] == ["INV2-B", "INV2-A", "INV2-C", "INV2-D"]
    summary = report.summary
    assert summary.total_invoices == 4
    assert summary.open_count == 2
    assert summary.overdue_count == 1
    assert summary.draft_count == 1
    usd = summary.totals_by_currency[0]
    assert usd.currency_code == "USD"
    assert usd.outstanding_amount == Decimal("3550.00")
    assert usd.overdue_amount == Decimal("1200.00")
    assert usd.draft_amount == Decimal("300.00")
