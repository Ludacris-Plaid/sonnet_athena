from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    client_type: str = "buyer"
    budget_max: Optional[float] = None
    preferred_city: Optional[str] = None
    pre_approved: bool = False
    timeline: Optional[str] = None
    lead_source: Optional[str] = None
    pipeline_stage: str = "lead"
    lead_temperature: str = "warm"
    deal_value: Optional[float] = None
    referred_by_client_id: Optional[str] = None
    household_name: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    client_type: Optional[str] = None
    status: Optional[str] = None
    budget_max: Optional[float] = None
    preferred_city: Optional[str] = None
    pre_approved: Optional[bool] = None
    timeline: Optional[str] = None
    lead_source: Optional[str] = None
    lead_temperature: Optional[str] = None
    deal_value: Optional[float] = None
    do_not_contact: Optional[bool] = None
    email_opt_in: Optional[bool] = None
    sms_opt_in: Optional[bool] = None
    next_follow_up_at: Optional[datetime] = None
    household_name: Optional[str] = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    client_type: str
    status: str
    budget_max: Optional[float] = None
    preferred_city: Optional[str] = None
    pre_approved: bool
    timeline: Optional[str] = None
    pipeline_stage: str
    lead_temperature: str
    lead_source: Optional[str] = None
    tags: Optional[list] = None
    deal_value: Optional[float] = None
    household_name: Optional[str] = None
    do_not_contact: bool
    email_opt_in: bool
    sms_opt_in: bool
    last_contacted_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    engagement_score: Optional[float] = None
    external_provider: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StageChangeRequest(BaseModel):
    new_stage: str


class TagRequest(BaseModel):
    tag: str


class NoteCreate(BaseModel):
    body: str


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    body: str
    created_at: datetime


class TaskCreate(BaseModel):
    title: str
    due_at: Optional[datetime] = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    due_at: Optional[datetime] = None
    is_completed: bool
    created_at: datetime


class SavedSearchCreate(BaseModel):
    name: str
    city: Optional[str] = None
    min_beds: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    property_type: Optional[str] = None


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    city: Optional[str] = None
    min_beds: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    is_active: bool


class MergeRequest(BaseModel):
    primary_id: str
    duplicate_id: str
