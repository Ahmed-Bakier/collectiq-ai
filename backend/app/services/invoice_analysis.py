"""Deterministic invoice analysis.

All rules are plain, tested Python - never LLM output. The AI agent only
explains and acts on these results. Missing data is reported, never guessed.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.schemas.analysis import (
    AnalysisSummary,
    AnalyzedInvoice,
    CollectionState,
    CurrencyTotals,
    InvoiceAnalysisResponse,
    PriorityLevel,
    SuggestedAction,
)
from app.schemas.invoices import InvoiceSummary

DUE_SOON_WINDOW_DAYS = 3

# PayPal statuses where money is still expected from the client.
COLLECTIBLE_STATUSES = frozenset({"SENT", "UNPAID", "PARTIALLY_PAID", "SHARED"})
PENDING_STATUSES = frozenset({"PAYMENT_PENDING", "SCHEDULED"})
CLOSED_STATUSES = frozenset(
    {
        "PAID",
        "MARKED_AS_PAID",
        "PAID_EXTERNAL",
        "CANCELLED",
        "AUTO_CANCELLED",
        "REFUNDED",
        "PARTIALLY_REFUNDED",
        "MARKED_AS_REFUNDED",
        "REFUNDED_EXTERNAL",
    }
)
DRAFT_STATUS = "DRAFT"

OPEN_STATES = frozenset(
    {
        CollectionState.OVERDUE,
        CollectionState.DUE_TODAY,
        CollectionState.DUE_SOON,
        CollectionState.NOT_DUE,
        CollectionState.NO_DUE_DATE,
    }
)

# Amount thresholds apply in the invoice's own currency (no FX conversion).
LARGE_AMOUNT = Decimal("1000")
MEDIUM_AMOUNT = Decimal("500")

HIGH_PRIORITY_MIN = 60
MEDIUM_PRIORITY_MIN = 35
MAX_OVERDUE_BONUS = 30
POINTS_PER_OVERDUE_DAY = 3

_BASE_SCORES: dict[CollectionState, int] = {
    CollectionState.OVERDUE: 50,
    CollectionState.DUE_TODAY: 40,
    CollectionState.DUE_SOON: 25,
    CollectionState.DRAFT: 20,
    CollectionState.NOT_DUE: 5,
}

_ACTIONS: dict[CollectionState, SuggestedAction] = {
    CollectionState.OVERDUE: SuggestedAction.SEND_REMINDER,
    CollectionState.DUE_TODAY: SuggestedAction.SEND_REMINDER,
    CollectionState.DUE_SOON: SuggestedAction.MONITOR,
    CollectionState.NOT_DUE: SuggestedAction.NONE,
    CollectionState.NO_DUE_DATE: SuggestedAction.REVIEW,
    CollectionState.DRAFT: SuggestedAction.SEND_INVOICE,
    CollectionState.PENDING: SuggestedAction.NONE,
    CollectionState.CLOSED: SuggestedAction.NONE,
    CollectionState.UNKNOWN: SuggestedAction.REVIEW,
}


def collectible_amount(invoice: InvoiceSummary) -> Decimal | None:
    """Amount still owed: amount_due when PayPal provides it, otherwise the total."""
    return invoice.amount_due if invoice.amount_due is not None else invoice.total_amount


def classify(invoice: InvoiceSummary, today: date) -> tuple[CollectionState, int | None]:
    """Return the collection state and days until due (negative means overdue)."""
    status = invoice.status.upper()
    days_until_due = (invoice.due_date - today).days if invoice.due_date else None

    if status == DRAFT_STATUS:
        return CollectionState.DRAFT, days_until_due
    if status in CLOSED_STATUSES:
        return CollectionState.CLOSED, None
    if status in PENDING_STATUSES:
        return CollectionState.PENDING, None
    if status not in COLLECTIBLE_STATUSES:
        return CollectionState.UNKNOWN, None
    if days_until_due is None:
        return CollectionState.NO_DUE_DATE, None
    if days_until_due < 0:
        return CollectionState.OVERDUE, days_until_due
    if days_until_due == 0:
        return CollectionState.DUE_TODAY, 0
    if days_until_due <= DUE_SOON_WINDOW_DAYS:
        return CollectionState.DUE_SOON, days_until_due
    return CollectionState.NOT_DUE, days_until_due


def priority_score(state: CollectionState, days_overdue: int | None, amount: Decimal | None) -> int:
    base = _BASE_SCORES.get(state, 0)
    if base == 0:
        return 0

    score = base
    if state is CollectionState.OVERDUE and days_overdue:
        score += min(days_overdue * POINTS_PER_OVERDUE_DAY, MAX_OVERDUE_BONUS)
    if amount is not None:
        if amount >= LARGE_AMOUNT:
            score += 20
        elif amount >= MEDIUM_AMOUNT:
            score += 10
    return min(score, 100)


def priority_level(score: int) -> PriorityLevel:
    if score >= HIGH_PRIORITY_MIN:
        return PriorityLevel.HIGH
    if score >= MEDIUM_PRIORITY_MIN:
        return PriorityLevel.MEDIUM
    if score > 0:
        return PriorityLevel.LOW
    return PriorityLevel.NONE


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def build_reasons(
    invoice: InvoiceSummary,
    state: CollectionState,
    days_until_due: int | None,
    amount: Decimal | None,
) -> list[str]:
    """Short, factual evidence shown to the user and passed to the agent."""
    reasons = [f"PayPal status: {invoice.status}"]

    if state is CollectionState.OVERDUE and days_until_due is not None:
        reasons.append(f"Due date {invoice.due_date} passed {_days(-days_until_due)} ago")
    elif state is CollectionState.DUE_TODAY:
        reasons.append(f"Due today ({invoice.due_date})")
    elif state in (CollectionState.DUE_SOON, CollectionState.NOT_DUE) and days_until_due is not None:
        reasons.append(f"Due in {_days(days_until_due)} on {invoice.due_date}")
    elif state is CollectionState.NO_DUE_DATE:
        reasons.append("PayPal provided no due date, so overdue status cannot be determined")
    elif state is CollectionState.DRAFT:
        reasons.append("Draft invoice has not been sent to the client yet")
    elif state is CollectionState.UNKNOWN:
        reasons.append("Unrecognized PayPal status; manual review required")

    if amount is None:
        reasons.append("Amount owed is unknown")
    else:
        reasons.append(f"Amount owed: {amount} {invoice.currency_code or ''}".rstrip())
    return reasons


def analyze_invoice(invoice: InvoiceSummary, today: date) -> AnalyzedInvoice:
    state, days_until_due = classify(invoice, today)
    days_overdue = -days_until_due if state is CollectionState.OVERDUE and days_until_due is not None else None
    amount = collectible_amount(invoice)
    score = priority_score(state, days_overdue, amount)

    return AnalyzedInvoice(
        invoice=invoice,
        collection_state=state,
        days_overdue=days_overdue,
        days_until_due=None if state is CollectionState.OVERDUE else days_until_due,
        priority_score=score,
        priority_level=priority_level(score),
        suggested_action=_ACTIONS[state],
        reasons=build_reasons(invoice, state, days_until_due, amount),
    )


def summarize(analyzed: list[AnalyzedInvoice]) -> AnalysisSummary:
    totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"outstanding": Decimal("0"), "overdue": Decimal("0"), "draft": Decimal("0")}
    )

    for item in analyzed:
        amount = collectible_amount(item.invoice)
        currency = item.invoice.currency_code
        if amount is None or currency is None:
            continue
        if item.collection_state in OPEN_STATES:
            totals[currency]["outstanding"] += amount
        if item.collection_state is CollectionState.OVERDUE:
            totals[currency]["overdue"] += amount
        if item.collection_state is CollectionState.DRAFT:
            totals[currency]["draft"] += amount

    def count(*states: CollectionState) -> int:
        return sum(1 for item in analyzed if item.collection_state in states)

    return AnalysisSummary(
        total_invoices=len(analyzed),
        open_count=count(*OPEN_STATES),
        overdue_count=count(CollectionState.OVERDUE),
        due_soon_count=count(CollectionState.DUE_TODAY, CollectionState.DUE_SOON),
        draft_count=count(CollectionState.DRAFT),
        needs_review_count=count(CollectionState.NO_DUE_DATE, CollectionState.UNKNOWN),
        totals_by_currency=[
            CurrencyTotals(
                currency_code=currency,
                outstanding_amount=values["outstanding"],
                overdue_amount=values["overdue"],
                draft_amount=values["draft"],
            )
            for currency, values in sorted(totals.items())
        ],
    )


def analyze_invoices(
    invoices: list[InvoiceSummary],
    today: date,
    timezone: str,
) -> InvoiceAnalysisResponse:
    """Analyze all invoices and sort them by priority (highest first)."""
    analyzed = [analyze_invoice(invoice, today) for invoice in invoices]
    analyzed.sort(
        key=lambda item: (-item.priority_score, item.invoice.due_date or date.max, item.invoice.id)
    )
    return InvoiceAnalysisResponse(
        as_of=today,
        timezone=timezone,
        due_soon_window_days=DUE_SOON_WINDOW_DAYS,
        summary=summarize(analyzed),
        invoices=analyzed,
    )
