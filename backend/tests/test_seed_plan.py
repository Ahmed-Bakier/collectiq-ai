"""Tests for the Sandbox seed plan (pure functions, no PayPal calls)."""

from datetime import date

from scripts.seed_sandbox_invoices import (
    INVOICE_NUMBER_MAX_LENGTH,
    SEED_INVOICES,
    build_invoice_number,
    build_invoice_payload,
)


def test_invoice_number_fits_paypal_limit() -> None:
    assert len(build_invoice_number("2611041930", 99)) <= INVOICE_NUMBER_MAX_LENGTH


def test_payload_contains_expected_dates_and_amount() -> None:
    payload = build_invoice_payload(
        SEED_INVOICES[0], "CIQ-TEST-01", date(2026, 11, 4), "merchant@business.example.com"
    )

    assert payload["detail"]["invoice_date"] == "2026-11-04"
    assert payload["detail"]["payment_term"] == {
        "term_type": "DUE_ON_DATE_SPECIFIED",
        "due_date": "2026-11-05",
    }
    assert payload["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "1200.00"}
    assert payload["invoicer"]["email_address"] == "merchant@business.example.com"


def test_seed_recipients_only_use_reserved_example_domain() -> None:
    assert all(seed.contact_email.endswith("@example.com") for seed in SEED_INVOICES)


def test_due_dates_are_never_before_invoice_date() -> None:
    assert all(seed.due_in_days >= 0 for seed in SEED_INVOICES)


def test_plan_includes_at_least_one_draft_for_the_agent_demo() -> None:
    assert any(not seed.send for seed in SEED_INVOICES)
