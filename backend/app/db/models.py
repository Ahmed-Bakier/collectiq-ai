"""Database models.

PayPal stays the source of truth for invoices. These tables only record what
CollectIQ proposed, what the user decided, and what was executed and verified.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.schemas.actions import ApprovalStatus, ExecutionStatus, VerificationStatus


class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_message: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)

    actions: Mapped[list["ActionRecord"]] = relationship(back_populates="run")


class ActionRecord(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    invoice_id: Mapped[str] = mapped_column(String(30), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(25), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    message_to_client: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Exact parameters that would be sent to PayPal, plus their fingerprint.
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    parameters_hash: Mapped[str] = mapped_column(String(64))
    approved_parameters_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Approval, execution and verification are tracked separately.
    approval_status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDING.value, index=True)
    execution_status: Mapped[str] = mapped_column(String(20), default=ExecutionStatus.NOT_STARTED.value)
    verification_status: Mapped[str] = mapped_column(
        String(16), default=VerificationStatus.NOT_VERIFIED.value
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRunRecord] = relationship(back_populates="actions")


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    actor: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    invoice_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AutopilotSettingsRecord(Base):
    """Single-row table with the user's autopilot policy (id is always 1)."""

    __tablename__ = "autopilot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approve_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_approve_max_amount: Mapped[str] = mapped_column(String(20), default="500.00")
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
