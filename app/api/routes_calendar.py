from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.calendar import EventCreate, EventUpdate, EventOut, ReminderCreate, ReminderOut
from app.services import calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events", response_model=list[EventOut])
def list_events(start: datetime, end: datetime, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return calendar_service.list_events(db, str(user.org_id), start, end)


@router.get("/events/today", response_model=list[EventOut])
def todays_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return calendar_service.get_todays_events(db, str(user.org_id), str(user.id))


@router.post("/events", response_model=EventOut)
def create_event(payload: EventCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return calendar_service.create_event(db, str(user.org_id), str(user.id), **payload.model_dump())


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(event_id: UUID, payload: EventUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return calendar_service.update_event(db, str(event_id), payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/events/{event_id}")
def delete_event(event_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    calendar_service.delete_event(db, str(event_id))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Reminders — time/date + a quick note, separate from full calendar events
# ---------------------------------------------------------------------------

@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(start: datetime | None = None, end: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return calendar_service.list_reminders(db, str(user.org_id), start, end)


@router.post("/reminders", response_model=ReminderOut)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return calendar_service.create_reminder(db, str(user.org_id), str(user.id), payload.note, payload.remind_at, payload.client_id)


@router.post("/reminders/{reminder_id}/complete", response_model=ReminderOut)
def complete_reminder(reminder_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return calendar_service.complete_reminder(db, str(reminder_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    calendar_service.delete_reminder(db, str(reminder_id))
    return {"ok": True}
