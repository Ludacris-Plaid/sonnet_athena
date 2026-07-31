import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean, JSON, Integer, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CRMProvider(str, PyEnum):
    FOLLOWUPBOSS = "followupboss"
    HUBSPOT = "hubspot"
    CSV = "csv"  # not a live connection — represents manual CSV import history


class SyncDirection(str, PyEnum):
    IMPORT_ONLY = "import_only"    # pull contacts FROM the CRM into RealtyAI
    EXPORT_ONLY = "export_only"    # push RealtyAI clients TO the CRM
    TWO_WAY = "two_way"


class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    provider = Column(Enum(CRMProvider), nullable=False)
    sync_direction = Column(Enum(SyncDirection), default=SyncDirection.IMPORT_ONLY)

    # Credentials are encrypted at rest — see app/services/crm_credential_service.py.
    # This column holds the ENCRYPTED blob, never plaintext.
    encrypted_credentials = Column(Text, nullable=False)

    # Per-connection secret used in the webhook URL path as a lightweight
    # verification layer (in addition to any provider-specific signature
    # check — see crm_connectors/*.py verify_webhook_signature()).
    webhook_secret = Column(String, nullable=False)

    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)  # "success" | "error" | null

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CRMSyncLog(Base):
    __tablename__ = "crm_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("crm_connections.id"), nullable=False)

    trigger = Column(String, default="manual")  # "manual" | "webhook" | "scheduled"
    status = Column(String, default="running")  # "running" | "success" | "error"

    contacts_imported = Column(Integer, default=0)
    contacts_updated = Column(Integer, default=0)
    contacts_exported = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)

    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
