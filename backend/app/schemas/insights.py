"""Client payment intelligence and collections forecast API models."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NEW = "new"  # No payment history yet.


class ClientInsight(BaseModel):
    client: str
    currency_code: str | None = None
    invoice_count: int
    paid_count: int
    on_time_count: int
    on_time_rate: float | None = None  # 0..1; None without payment history.
    avg_days_late: float | None = None  # Early payments count as 0 days late.
    max_days_late: int | None = None
    open_count: int
    open_amount: Decimal
    overdue_amount: Decimal
    oldest_overdue_days: int | None = None
    risk_level: RiskLevel
    risk_reasons: list[str]


class ForecastBucket(BaseModel):
    label: str
    start: date
    end: date
    expected_amount: Decimal  # Expected from clients that are not at risk.
    at_risk_amount: Decimal  # Expected, but from at-risk invoices.
    invoice_count: int


class ForecastInvoice(BaseModel):
    invoice_id: str
    invoice_number: str | None = None
    client: str
    amount: Decimal
    due_date: date
    expected_date: date
    risk_level: RiskLevel
    at_risk: bool


class CashFlowForecast(BaseModel):
    currency_code: str | None = None
    horizon_days: int
    total_open: Decimal
    expected_within_horizon: Decimal
    expected_later: Decimal
    at_risk_amount: Decimal
    unscheduled_amount: Decimal  # Open invoices without a due date.
    buckets: list[ForecastBucket]
    invoices: list[ForecastInvoice]
    method: str


class InsightsResponse(BaseModel):
    as_of: date
    timezone: str
    clients: list[ClientInsight]  # Highest risk first.
    forecast: CashFlowForecast
