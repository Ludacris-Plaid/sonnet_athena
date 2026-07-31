from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CRMConnectionCreate(BaseModel):
    provider: str  # "followupboss" | "hubspot"
    sync_direction: str = "import_only"
    credentials: dict  # e.g. {"api_key": "..."} or {"access_token": "..."}


class CRMConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    sync_direction: str
    is_active: bool
    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    created_at: datetime


class CRMSyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger: str
    status: str
    contacts_imported: int
    contacts_updated: int
    contacts_exported: int
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
