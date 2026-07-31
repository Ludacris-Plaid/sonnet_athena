"""
Local calendar CRUD. Sync with Google/Microsoft lives in
calendar_sync_service.py — this module only touches the local
CalendarEvent table, same separation as client_service.py vs
crm_sync_service.py.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent, CalendarProvider


def create_event(db: Session, org_id: str, user_id: str, **fields) -> CalendarEvent:
    event = CalendarEvent(org_id=org_id, user_id=user_id, provider=CalendarProvider.LOCAL, sync_pending=False, **fields)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event(db: Session, event_id: str) -> CalendarEvent | None:
    return db.query(CalendarEvent).filter(CalendarEvent.id == event_id).first()


def list_events(db: Session, org_id: str, start: datetime, end: datetime, user_id: str | None = None) -> list[CalendarEvent]:
    query = db.query(CalendarEvent).filter(
        CalendarEvent.org_id == org_id,
        CalendarEvent.start_at < end,
        CalendarEvent.end_at > start,
    )
    if user_id:
        query = query.filter(CalendarEvent.user_id == user_id)
    return query.order_by(CalendarEvent.start_at).all()


def get_todays_events(db: Session, org_id: str, user_id: str) -> list[CalendarEvent]:
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)
    return list_events(db, org_id, start, end, user_id)


def update_event(db: Session, event_id: str, updates: dict) -> CalendarEvent:
    event = get_event(db, event_id)
    if not event:
        raise ValueError("Event not found")
    for key, value in updates.items():
        if value is not None and hasattr(event, key):
            setattr(event, key, value)
    # A local edit to a previously-synced event needs to be pushed back to
    # the remote calendar — flag it rather than silently letting it drift.
    if event.provider != CalendarProvider.LOCAL:
        event.sync_pending = True
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def delete_event(db: Session, event_id: str) -> None:
    event = get_event(db, event_id)
    if event:
        db.delete(event)
        db.commit()


# ---------------------------------------------------------------------------
# Reminders — separate from events, see Reminder's docstring
# ---------------------------------------------------------------------------

def create_reminder(db: Session, org_id: str, user_id: str, note: str, remind_at, client_id: str | None = None) -> "Reminder":
    from app.models.calendar_event import Reminder
    reminder = Reminder(org_id=org_id, user_id=user_id, note=note, remind_at=remind_at, client_id=client_id)
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def list_reminders(db: Session, org_id: str, start=None, end=None, include_completed: bool = False) -> list:
    from app.models.calendar_event import Reminder
    query = db.query(Reminder).filter(Reminder.org_id == org_id)
    if not include_completed:
        query = query.filter(Reminder.is_completed == False)  # noqa: E712
    if start:
        query = query.filter(Reminder.remind_at >= start)
    if end:
        query = query.filter(Reminder.remind_at < end)
    return query.order_by(Reminder.remind_at).all()


def complete_reminder(db: Session, reminder_id: str) -> "Reminder":
    from app.models.calendar_event import Reminder
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise ValueError("Reminder not found")
    reminder.is_completed = True
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def delete_reminder(db: Session, reminder_id: str) -> None:
    from app.models.calendar_event import Reminder
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if reminder:
        db.delete(reminder)
        db.commit()
