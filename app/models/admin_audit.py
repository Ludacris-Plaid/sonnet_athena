import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AdminAuditLog(Base):
    """
    Every admin action lands here — whether triggered by a button click in
    the admin UI or by the admin's Athena via the tool-calling agent. This
    is the accountability half of "god mode with guardrails": the AI (and
    the human admin) can do a lot, but nothing happens without a permanent,
    queryable record of who did what, when, and why.
    """
    __tablename__ = "admin_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_user_id = Column(UUID(as_uuid=True), nullable=False)
    admin_email = Column(String, nullable=True)  # denormalized for readability even if the user is later deleted

    action = Column(String, nullable=False)  # e.g. "suspend_user", "adjust_plan_tier"
    target_type = Column(String, nullable=True)  # "user" | "organization" | "invite_code" | None
    target_id = Column(String, nullable=True)

    source = Column(String, default="ui")  # "ui" | "agent" — was this a button click or the admin AI assistant?
    detail = Column(JSON, nullable=True)  # arbitrary extra context (reason, before/after values, etc.)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
