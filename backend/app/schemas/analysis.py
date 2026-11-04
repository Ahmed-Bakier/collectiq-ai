"""Invoice analysis API models."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from app.schemas.invoices import InvoiceSummary


class CollectionState(StrEnum):
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    DUE_SOON = "due_soon"
    NOT_DUE = "not_due"
    NO_DUE_DATE = "no_due_date"
    DRAFT = "draft"
    PENDING = "pending"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class PriorityLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class SuggestedAction(StrEnum):
    """Deterministic action eligibility. The agent may only propose these."""

    SEND_REMINDER = "send_reminder"
    SEND_INVOICE = "send_invoice"
    MONITOR = "monitor"
    REVIEW = "review"
    NONE = "none"


class AnalyzedInvoice(BaseModel):
    invoice: InvoiceSummary
    collection_state: CollectionState
    days_overdue: int | None = None
    days_until_due: int | None = None
    priority_score: int
    priority_level: PriorityLevel
    suggested_action: SuggestedAction
    reasons: list[str]


class CurrencyTotals(BaseModel):
    """Totals per currency. Amounts are never converted between currencies."""

    currency_code: str
    outstanding_amount: Decimal
    overdue_amount: Decimal
    draft_amount: Decimal


class AnalysisSummary(BaseModel):
    total_invoices: int
    open_count: int
    overdue_count: int
    due_soon_count: int  # Due today or within the due-soon window.
    draft_count: int
    needs_review_count: int
    totals_by_currency: list[CurrencyTotals]


class InvoiceAnalysisResponse(BaseModel):
    as_of: date
    timezone: str
    due_soon_window_days: int
    summary: AnalysisSummary
    invoices: list[AnalyzedInvoice]  # Sorted by priority, highest first.
