import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CalendarProvider(str, PyEnum):
    LOCAL = "local"        # created directly in RealtyAI, no external calendar
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class CalendarEvent(Base):
    """
    Local calendar event. Events synced from Google/Microsoft are mirrored
    here (external_id + provider set) so the app has one calendar model to
    render regardless of source — see calendar_sync_service.py for the
    two-way sync logic.
    """
    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)

    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    location = Column(String, nullable=True)

    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)

    event_type = Column(String, default="general")  # "showing" | "closing" | "call" | "meeting" | "general"

    # External calendar sync
    provider = Column(Enum(CalendarProvider), default=CalendarProvider.LOCAL)
    external_id = Column(String, nullable=True)   # the Google/Microsoft event ID
    external_etag = Column(String, nullable=True)  # for conflict detection on update
    last_synced_at = Column(DateTime, nullable=True)
    sync_pending = Column(Boolean, default=False)  # true when a local edit hasn't been pushed to the remote calendar yet

    attendees = Column(JSON, nullable=True)  # list[str] of emails

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CalendarConnection(Base):
    """
    A user's connected external calendar (Google or Microsoft), OAuth
    tokens encrypted at rest via crm_credential_service.py's same Fernet
    helper (generic enough to reuse — see calendar_sync_service.py).
    """
    __tablename__ = "calendar_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    provider = Column(Enum(CalendarProvider), nullable=False)
    encrypted_tokens = Column(String, nullable=False)  # {"access_token", "refresh_token", "expires_at"}, encrypted JSON
    calendar_id = Column(String, default="primary")

    sync_direction = Column(String, default="two_way")  # "import_only" | "export_only" | "two_way"
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Reminder(Base):
    """
    A lightweight time/date + note reminder — deliberately separate from
    CalendarEvent (which has a start/end, a channel type, sync fields,
    etc). A reminder is just "remind me about X at Y," the kind of thing
    Athena herself suggested adding when asked what the platform was
    still missing.
    """
    __tablename__ = "reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)

    note = Column(String, nullable=False)
    remind_at = Column(DateTime, nullable=False)
    is_completed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
