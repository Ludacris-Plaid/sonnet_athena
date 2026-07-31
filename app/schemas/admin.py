from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    status: str
    status_reason: Optional[str] = None
    status_changed_at: Optional[datetime] = None
    created_at: datetime


class UpdateUserStatusRequest(BaseModel):
    status: str  # "active" | "suspended" | "banned"
    reason: Optional[str] = None


class UpdateUserProfileRequest(BaseModel):
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None


class AdjustPlanTierRequest(BaseModel):
    new_tier: str


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    admin_email: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    source: str
    detail: Optional[dict] = None
    created_at: datetime


class AdminChatRequest(BaseModel):
    message: str


class AdminChatResponse(BaseModel):
    reply: str
    conversation_id: str
