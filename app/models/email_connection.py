import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class EmailProvider(str, PyEnum):
    GMAIL = "gmail"
    MICROSOFT = "microsoft"


class EmailConnection(Base):
    """A user's connected external mailbox. OAuth tokens encrypted at rest."""
    __tablename__ = "email_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    provider = Column(Enum(EmailProvider), nullable=False)
    email_address = Column(String, nullable=False)
    encrypted_tokens = Column(String, nullable=False)  # {"access_token","refresh_token","expires_at"}, encrypted JSON

    history_id = Column(String, nullable=True)   # Gmail incremental-sync cursor
    delta_link = Column(String, nullable=True)    # Microsoft Graph incremental-sync cursor

    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SlackConnection(Base):
    """A workspace's Slack integration — bot token + signing secret, encrypted."""
    __tablename__ = "slack_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    team_id = Column(String, nullable=False)  # Slack workspace ID
    team_name = Column(String, nullable=True)
    encrypted_tokens = Column(String, nullable=False)  # {"bot_token","signing_secret"}, encrypted JSON
    notification_channel_id = Column(String, nullable=True)  # where system alerts get posted

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
