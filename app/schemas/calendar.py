from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    event_type: str = "general"
    client_id: Optional[str] = None
    attendees: Optional[list] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    event_type: Optional[str] = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: datetime
    all_day: bool
    event_type: str
    provider: str
    client_id: Optional[UUID] = None
    sync_pending: bool


class ReminderCreate(BaseModel):
    note: str
    remind_at: datetime
    client_id: Optional[str] = None


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    note: str
    remind_at: datetime
    is_completed: bool
    client_id: Optional[UUID] = None
