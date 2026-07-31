"""Reminders route: due reminders + preset schedule creation."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.calendar_event import CalendarEvent
import datetime as dt
import uuid

router = APIRouter(prefix="/reminders", tags=["reminders"])


PRESETS = [
    {"label": "Every morning", "icon": "☀️", "recurrence": "daily", "time": "09:00"},
    {"label": "Every evening", "icon": "🌙", "recurrence": "daily", "time": "18:00"},
    {"label": "Every Mon-Fri", "icon": "📅", "recurrence": "weekdays", "time": "09:00"},
    {"label": "Every Friday", "icon": "🎉", "recurrence": "weekly", "day": "fri", "time": "16:00"},
    {"label": "Weekly review", "icon": "📊", "recurrence": "weekly", "day": "mon", "time": "10:00"},
    {"label": "Monthly check-in", "icon": "🔁", "recurrence": "monthly", "time": "09:00"},
]


@router.post("/regenerate", response_model=None)
def regenerate_instances(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = dt.datetime.utcnow()
    events = db.query(CalendarEvent).filter(CalendarEvent.user_id == user.id, CalendarEvent.recurrence_type != None).all()
    for ev in events:
        last = db.query(CalendarEvent).filter(CalendarEvent.user_id == user.id, CalendarEvent.title == ev.title).order_by(CalendarEvent.start_at.desc()).first()
        if last and last.start_at and last.start_at < now and last.recurrence_type:
            nxt = _next_occurrence(last.start_at, last.recurrence_type, ev.start_at)
            if nxt < (ev.recurrence_end_date or now + dt.timedelta(days=365)):
                db.add(CalendarEvent(id=uuid.uuid4(), org_id=ev.org_id, user_id=ev.user_id, title=ev.title, event_type=ev.event_type or "general", start_at=nxt, end_at=nxt + (ev.end_at - ev.start_at) if ev.end_at else nxt + dt.timedelta(hours=1), location=ev.location))
    db.commit()
    return {"status": "regenerated"}

@router.get("/due")
def get_due_reminders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return reminders that are due right now (past due, not yet dismissed)."""
    now = dt.datetime.utcnow()
    due = db.query(CalendarEvent).filter(
        CalendarEvent.user_id == user.id,
        CalendarEvent.start_at <= now,
        CalendarEvent.end_at >= now,
    ).limit(10).all()
    return {
        "reminders": [{"id": str(r.id), "title": r.title, "due": str(r.start_at), "type": r.event_type} for r in due],
        "count": len(due),
    }


@router.post("/preset", response_model=None)
def create_preset(preset_key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Create a preset recurring event."""
    preset = next((p for p in PRESETS if p["label"].lower().replace(" ", "-") == preset_key), None)
    if not preset:
        raise HTTPException(400, f"Unknown preset: {preset_key}")
    now = dt.datetime.utcnow()
    start = now.replace(hour=int(preset["time"].split(":")[0]), minute=int(preset["time"].split(":")[1]), second=0)
    end = start + dt.timedelta(hours=1)
    event = CalendarEvent(
        id=uuid.uuid4(), org_id=user.org_id, user_id=user.id,
        title=preset["label"], event_type="general",
        start_at=start, end_at=end,
        recurrence_type=preset.get("recurrence"),
        recurrence_end_date=now + dt.timedelta(days=365),
    )
    db.add(event)
    # Generate all recurring instances up to end date
    if event.recurrence_type:
        _generate_instances(db, event)
    db.commit()
    db.refresh(event)
    return {"id": str(event.id), "title": event.title, "recurrence": event.recurrence_type}


@router.get("/presets")


def list_presets():

    return {"presets": PRESETS}

# --- Recurrence engine ---
def _generate_instances(db: Session, base: CalendarEvent):
    
    if not base.recurrence_type or not base.start_at or not base.recurrence_end_date:
        return
    rtype = base.recurrence_type
    current = base.start_at
    end = base.recurrence_end_date
    count = 0
    while current < end and count < 366:
        current = _next_occurrence(current, rtype, base.start_at)
        if current > end:
            break
        db.add(CalendarEvent(
            id=uuid.uuid4(), org_id=base.org_id, user_id=base.user_id,
            title=base.title, event_type=base.event_type or "general",
            start_at=current, end_at=current + (base.end_at - base.start_at),
            location=base.location,
        ))
        count += 1
    db.commit()


def _next_occurrence(prev: dt.datetime, rtype: str, original: dt.datetime) -> dt.datetime:
    
    if rtype == "daily":
        return prev + dt.timedelta(days=1)
    elif rtype == "weekly":
        return prev + dt.timedelta(days=7)
    elif rtype == "biweekly":
        return prev + dt.timedelta(days=14)
    elif rtype == "monthly":
        m = prev.month + 1
        y = prev.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        return prev.replace(year=y, month=m)
    elif rtype == "weekdays":
        n = prev + dt.timedelta(days=1)
        while n.weekday() >= 5:
            n += dt.timedelta(days=1)
        return n
    return prev + dt.timedelta(days=1)
