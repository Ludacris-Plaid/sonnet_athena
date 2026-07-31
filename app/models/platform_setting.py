import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PlatformSetting(Base):
    """
    Runtime-overridable configuration, encrypted at rest. Two scopes:
      - org_id set: an org-level integration key (voice provider, listings
        data source credentials, web search, Slack) — editable from the
        regular Settings page by any user in that org.
      - org_id NULL: a platform-wide infrastructure setting (DeepSeek,
        Supabase, OAuth app registration, Twilio account) — editable only
        from the Admin dashboard, since a mistaken or malicious edit here
        would affect every org on the platform, not just one.

    Resolution order (see settings_service.get_effective_setting): DB
    override first, then the .env-loaded default in config.py. This is
    what actually makes "add an API key in Settings" take effect without
    a server restart or editing .env by hand — .env remains the
    bootstrap/default layer, this is the runtime override layer.
    """
    __tablename__ = "platform_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)  # NULL = platform-wide

    key = Column(String, nullable=False)  # matches a Settings field name in config.py, e.g. "ELEVENLABS_API_KEY"
    encrypted_value = Column(String, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
