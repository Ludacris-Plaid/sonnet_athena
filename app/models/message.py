import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Channel(str, PyEnum):
    EMAIL = "email"
    SMS = "sms"
    VOICE = "voice"
    SLACK = "slack"
    MANUAL = "manual"


class MessageDirection(str, PyEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Message(Base):
    """
    Unified inbox: every inbound/outbound email, SMS, etc. lands here,
    normalized to one shape regardless of channel.
    """
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)

    channel = Column(Enum(Channel), nullable=False)
    direction = Column(Enum(MessageDirection), nullable=False)

    from_address = Column(String, nullable=True)  # email or phone
    to_address = Column(String, nullable=True)
    subject = Column(String, nullable=True)  # email only
    body = Column(String, nullable=False)

    # Athena's proposed draft replies (populated for inbound messages awaiting a reply)
    draft_replies = Column(JSON, nullable=True)  # list[{"tone": "professional", "body": "..."}]

    # Whether this outbound message was sent autonomously by Athena vs. approved by the user
    sent_autonomously = Column(Boolean, default=False)
    was_edited_before_send = Column(Boolean, default=False)

    # Fair housing compliance flag on outbound content. For email/SMS this is
    # informational (the human already approved the send). For voice, this
    # is enforced BEFORE synthesis — see voice_conversation_service.py —
    # because voice sends autonomously with no human review step to catch it.
    compliance_flagged = Column(Boolean, default=False)
    compliance_notes = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
