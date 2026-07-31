import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ActionType(str, PyEnum):
    SEND_EMAIL = "send_email"
    SEND_SMS = "send_sms"
    SCHEDULE_EVENT = "schedule_event"
    UPDATE_CLIENT = "update_client"


class AutomationLevel(str, PyEnum):
    DRAFT_ONLY = "draft_only"          # Athena always proposes, never sends
    LIMITED_AUTONOMY = "limited_autonomy"  # Athena can act on low-risk items only
    FULL_AUTONOMY = "full_autonomy"    # Athena acts, logs it, user reviews after the fact


class TrustScore(Base):
    """
    Per-user, per-action-type trust score that gates how much autonomy
    Athena is granted. This is the core of the 'trust ladder'.
    """
    __tablename__ = "trust_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(Enum(ActionType), nullable=False)

    score = Column(Float, default=0.0)  # 0-100
    automation_level = Column(Enum(AutomationLevel), default=AutomationLevel.DRAFT_ONLY)

    total_actions = Column(Integer, default=0)
    actions_sent_unedited = Column(Integer, default=0)
    actions_edited = Column(Integer, default=0)
    actions_rejected = Column(Integer, default=0)

    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TrustEvent(Base):
    """Audit log of every outcome that fed into a trust score adjustment."""
    __tablename__ = "trust_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(Enum(ActionType), nullable=False)

    outcome = Column(String, nullable=False)  # "sent_unedited" | "edited" | "rejected"
    score_delta = Column(Float, nullable=False)
    resulting_score = Column(Float, nullable=False)

    related_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrustBadge(Base):
    """
    Earned badges — persisted (not recomputed fresh each time) so
    earned_at is stable and a badge doesn't flicker in and out if the
    underlying stats hover right at a threshold. Definitions and award
    criteria live in trust_gamification_service.py, not here — this is
    just the record of what's been earned.
    """
    __tablename__ = "trust_badges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    badge_key = Column(String, nullable=False)  # matches a key in BADGE_DEFINITIONS
    earned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
