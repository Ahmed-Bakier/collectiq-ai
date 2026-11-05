"""Client payment intelligence and a 30-day collections forecast.

Deterministic and explainable: computed only from PayPal invoices and the
payments recorded on them. The AI agent reads these results; it never
computes or overrides them. Missing data is excluded, never guessed.
"""

import asyncio
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.integrations.paypal.exceptions import PayPalError
from app.integrations.paypal.schemas import PayPalInvoice
from app.schemas.analysis import CollectionState
from app.schemas.insights import (
    CashFlowForecast,
    ClientInsight,
    ForecastBucket,
    ForecastInvoice,
    InsightsResponse,
    RiskLevel,
)
from app.schemas.invoices import InvoiceSummary
from app.services.invoice_analysis import OPEN_STATES, classify, collectible_amount
from app.services.invoices import InvoiceService, to_invoice_summary

PAID_STATUSES = frozenset({"PAID", "MARKED_AS_PAID", "PAID_EXTERNAL"})
DRAFT_STATUS = "DRAFT"

FORECAST_HORIZON_DAYS = 30
BUCKET_STARTS = (0, 7, 14, 21)  # Four buckets; the last one runs to the end of the horizon.
DETAIL_CONCURRENCY = 5

LOW_RISK_MAX_AVG_LATE = 3.0
LOW_RISK_MIN_ON_TIME = 0.8
HIGH_RISK_MIN_AVG_LATE = 14.0
SEVERE_OVERDUE_DAYS = 30
AT_RISK_OVERDUE_DAYS = 21

RISK_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.NEW: 2, RiskLevel.LOW: 3}
ZERO = Decimal("0")
FORECAST_METHOD = (
    "Expected date = due date + the client's average days late from PayPal payment history "
    "(0 for new clients); overdue invoices are expected from today. At risk = high-risk client "
    f"or more than {AT_RISK_OVERDUE_DAYS} days overdue."
)


@dataclass(frozen=True)
class InvoiceFacts:
    summary: InvoiceSummary
    client: str
    paid_on: date | None


def client_key(summary: InvoiceSummary) -> str:
    return (
        summary.recipient_business_name
        or summary.recipient_name
        or summary.recipient_email
        or "Unknown client"
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def paid_date(invoice: PayPalInvoice) -> date | None:
    """Date a fully paid invoice was settled (the latest recorded payment)."""
    if invoice.status.upper() not in PAID_STATUSES or invoice.payments is None:
        return None
    dates = [
        parsed
        for parsed in (_parse_date(transaction.payment_date) for transaction in invoice.payments.transactions)
        if parsed is not None
    ]
    return max(dates) if dates else None


def assess_risk(
    paid_count: int,
    on_time_rate: float | None,
    avg_days_late: float | None,
    oldest_overdue_days: int | None,
) -> tuple[RiskLevel, list[str]]:
    """Explainable risk level from payment history and the oldest overdue invoice."""
    severe = oldest_overdue_days is not None and oldest_overdue_days > SEVERE_OVERDUE_DAYS
    has_history = paid_count > 0 and on_time_rate is not None and avg_days_late is not None

    reasons: list[str] = []
    if has_history:
        reasons.append(
            f"Paid {round(on_time_rate * 100)}% of {paid_count} invoice(s) on time; "
            f"on average {avg_days_late:.1f} days late"
        )
    else:
        reasons.append("No paid invoices yet, so there is no payment history")
    if severe:
        reasons.append(f"An open invoice is {oldest_overdue_days} days overdue")

    if severe:
        return RiskLevel.HIGH, reasons
    if not has_history:
        return RiskLevel.NEW, reasons
    if avg_days_late > HIGH_RISK_MIN_AVG_LATE:
        return RiskLevel.HIGH, reasons
    if avg_days_late <= LOW_RISK_MAX_AVG_LATE and on_time_rate >= LOW_RISK_MIN_ON_TIME:
        return RiskLevel.LOW, reasons
    return RiskLevel.MEDIUM, reasons


def build_client_insights(facts: list[InvoiceFacts], today: date) -> list[ClientInsight]:
    grouped: dict[str, list[InvoiceFacts]] = defaultdict(list)
    for fact in facts:
        if fact.summary.status.upper() != DRAFT_STATUS:
            grouped[fact.client].append(fact)

    insights: list[ClientInsight] = []
    for client, items in grouped.items():
        currencies = Counter(item.summary.currency_code for item in items if item.summary.currency_code)
        currency = currencies.most_common(1)[0][0] if currencies else None

        lateness: list[int] = []
        on_time = 0
        open_count = 0
        open_amount = ZERO
        overdue_amount = ZERO
        oldest_overdue: int | None = None

        for item in items:
            summary = item.summary
            if item.paid_on is not None and summary.due_date is not None:
                delta = (item.paid_on - summary.due_date).days
                lateness.append(max(delta, 0))
                if delta <= 0:
                    on_time += 1

            state, days_until_due = classify(summary, today)
            amount = collectible_amount(summary)
            if state not in OPEN_STATES or amount is None or summary.currency_code != currency:
                continue
            open_count += 1
            open_amount += amount
            if state is CollectionState.OVERDUE and days_until_due is not None:
                overdue_amount += amount
                oldest_overdue = max(oldest_overdue or 0, -days_until_due)

        paid_count = len(lateness)
        on_time_rate = round(on_time / paid_count, 2) if paid_count else None
        avg_days_late = round(sum(lateness) / paid_count, 1) if paid_count else None
        level, reasons = assess_risk(paid_count, on_time_rate, avg_days_late, oldest_overdue)

        insights.append(
            ClientInsight(
                client=client,
                currency_code=currency,
                invoice_count=len(items),
                paid_count=paid_count,
                on_time_count=on_time,
                on_time_rate=on_time_rate,
                avg_days_late=avg_days_late,
                max_days_late=max(lateness) if lateness else None,
                open_count=open_count,
                open_amount=open_amount,
                overdue_amount=overdue_amount,
                oldest_overdue_days=oldest_overdue,
                risk_level=level,
                risk_reasons=reasons,
            )
        )

    insights.sort(
        key=lambda insight: (
            RISK_ORDER[insight.risk_level],
            -insight.overdue_amount,
            -insight.open_amount,
            insight.client,
        )
    )
    return insights


def _bucket_label(start: date, end: date) -> str:
    return f"{start:%b} {start.day} – {end:%b} {end.day}"


def build_forecast(facts: list[InvoiceFacts], clients: dict[str, ClientInsight], today: date) -> CashFlowForecast:
    """Expected collections over the next 30 days, in the main currency (no FX conversion)."""
    open_items: list[tuple[InvoiceFacts, Decimal]] = []
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for fact in facts:
        state, _ = classify(fact.summary, today)
        amount = collectible_amount(fact.summary)
        currency = fact.summary.currency_code
        if state in OPEN_STATES and amount is not None and currency:
            open_items.append((fact, amount))
            totals[currency] += amount
    currency = max(totals, key=lambda code: totals[code]) if totals else None

    horizon_end = today + timedelta(days=FORECAST_HORIZON_DAYS - 1)
    bounds: list[tuple[date, date]] = []
    for index, offset in enumerate(BUCKET_STARTS):
        start = today + timedelta(days=offset)
        end = (
            today + timedelta(days=BUCKET_STARTS[index + 1] - 1)
            if index + 1 < len(BUCKET_STARTS)
            else horizon_end
        )
        bounds.append((start, end))

    expected = [ZERO] * len(bounds)
    at_risk = [ZERO] * len(bounds)
    counts = [0] * len(bounds)
    total_open = later = at_risk_total = unscheduled = ZERO
    rows: list[ForecastInvoice] = []

    for fact, amount in open_items:
        summary = fact.summary
        if summary.currency_code != currency:
            continue
        total_open += amount
        if summary.due_date is None:
            unscheduled += amount
            continue

        insight = clients.get(fact.client)
        level = insight.risk_level if insight else RiskLevel.NEW
        delay = round(insight.avg_days_late) if insight and insight.avg_days_late is not None else 0
        expected_date = max(today, summary.due_date + timedelta(days=delay))
        flagged = level is RiskLevel.HIGH or (today - summary.due_date).days > AT_RISK_OVERDUE_DAYS
        if flagged:
            at_risk_total += amount

        if expected_date <= horizon_end:
            index = next(i for i, (start, end) in enumerate(bounds) if start <= expected_date <= end)
            counts[index] += 1
            if flagged:
                at_risk[index] += amount
            else:
                expected[index] += amount
        else:
            later += amount

        rows.append(
            ForecastInvoice(
                invoice_id=summary.id,
                invoice_number=summary.invoice_number,
                client=fact.client,
                amount=amount,
                due_date=summary.due_date,
                expected_date=expected_date,
                risk_level=level,
                at_risk=flagged,
            )
        )

    rows.sort(key=lambda row: (row.expected_date, row.client))
    buckets = [
        ForecastBucket(
            label=_bucket_label(start, end),
            start=start,
            end=end,
            expected_amount=expected[index],
            at_risk_amount=at_risk[index],
            invoice_count=counts[index],
        )
        for index, (start, end) in enumerate(bounds)
    ]
    return CashFlowForecast(
        currency_code=currency,
        horizon_days=FORECAST_HORIZON_DAYS,
        total_open=total_open,
        expected_within_horizon=sum(expected, ZERO) + sum(at_risk, ZERO),
        expected_later=later,
        at_risk_amount=at_risk_total,
        unscheduled_amount=unscheduled,
        buckets=buckets,
        invoices=rows,
        method=FORECAST_METHOD,
    )


def build_insights(invoices: list[PayPalInvoice], today: date, timezone: str) -> InsightsResponse:
    facts: list[InvoiceFacts] = []
    for invoice in invoices:
        summary = to_invoice_summary(invoice)
        facts.append(InvoiceFacts(summary=summary, client=client_key(summary), paid_on=paid_date(invoice)))

    clients = build_client_insights(facts, today)
    forecast = build_forecast(facts, {insight.client: insight for insight in clients}, today)
    return InsightsResponse(as_of=today, timezone=timezone, clients=clients, forecast=forecast)


class ClientInsightsService:
    """Loads PayPal invoices (with payment dates) and builds insights. Read-only."""

    def __init__(self, invoice_service: InvoiceService) -> None:
        self._service = invoice_service

    async def load_invoices(self) -> list[PayPalInvoice]:
        invoices = await self._service.list_all_raw_invoices()
        semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)

        async def with_payments(invoice: PayPalInvoice) -> PayPalInvoice:
            has_payments = invoice.payments is not None and bool(invoice.payments.transactions)
            if invoice.status.upper() not in PAID_STATUSES or has_payments:
                return invoice
            async with semaphore:
                try:
                    return await self._service.api.get_invoice(invoice.id)
                except (PayPalError, ValueError):
                    return invoice  # Payment date unknown: excluded from history, never guessed.

        return list(await asyncio.gather(*(with_payments(invoice) for invoice in invoices)))

    async def build(self, today: date, timezone: str) -> InsightsResponse:
        return build_insights(await self.load_invoices(), today, timezone)
