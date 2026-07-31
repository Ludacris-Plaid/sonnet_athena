"""
Deal Room — everything about one specific client/deal, aggregated in one
call. Built properly around real per-client relations (Message.client_id,
Document.client_id, CalendarEvent.client_id, and the existing matching
service for properties) rather than "the last 20 things in the whole org,"
which would show every agent's unrelated activity mixed into one deal's
view — the opposite of what a deal room is for.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.message import Message
from app.models.document import Document
from app.models.calendar_event import CalendarEvent
from app.services import client_service
from app.services.client_timeline_service import get_client_timeline
from app.services.matching_service import match_properties_for_client


def get_deal_room(db: Session, client_id: str, org_id: str) -> dict:
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == org_id).first()
    if not client:
        raise ValueError("Client not found")

    messages = (
        db.query(Message)
        .filter(Message.client_id == client.id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    documents = (
        db.query(Document)
        .filter(Document.client_id == client.id)
        .order_by(Document.created_at.desc())
        .limit(20)
        .all()
    )
    calendar_events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.client_id == client.id)
        .order_by(CalendarEvent.start_at.desc())
        .limit(10)
        .all()
    )
    matched_properties = match_properties_for_client(db, client, limit=5)
    tasks = client_service.list_tasks(db, str(client.id))
    notes = client_service.list_notes(db, str(client.id))
    saved_searches = client_service.list_saved_searches(db, str(client.id))
    timeline = get_client_timeline(db, str(client.id), limit=15)  # the real activity feed — every actual message/note/stage-change, not generic filler text

    days_since_last_contact = (
        (datetime.now(timezone.utc) - client.last_contacted_at.replace(tzinfo=timezone.utc)).days
        if client.last_contacted_at else None
    )

    return {
        "client": {
            "id": str(client.id),
            "name": client.name,
            "email": client.email,
            "phone": client.phone,
            "client_type": client.client_type,
            "pipeline_stage": client.pipeline_stage,
            "lead_temperature": client.lead_temperature,
            "tags": client.tags or [],
            "deal_value": client.deal_value,
            "engagement_score": client.engagement_score,
            "created_at": client.created_at.isoformat() if client.created_at else None,
            "days_since_last_contact": days_since_last_contact,
        },
        "matched_properties": matched_properties,
        "timeline": [{"type": e["type"], "summary": e["summary"], "timestamp": e["timestamp"].isoformat() if hasattr(e["timestamp"], "isoformat") else str(e["timestamp"])} for e in timeline],
        "recent_messages": [
            {
                "id": str(m.id), "direction": m.direction.value, "channel": m.channel.value,
                "body": (m.body or "")[:160], "created_at": m.created_at.isoformat() if m.created_at else None,
                "compliance_flagged": m.compliance_flagged,
            }
            for m in messages
        ],
        "documents": [
            {"id": str(d.id), "title": d.title, "doc_type": d.doc_type.value, "status": d.status.value, "created_at": d.created_at.isoformat() if d.created_at else None}
            for d in documents
        ],
        "calendar_events": [
            {"id": str(e.id), "title": e.title, "start_at": e.start_at.isoformat(), "event_type": e.event_type}
            for e in calendar_events
        ],
        "tasks": [{"id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None, "is_completed": t.is_completed} for t in tasks],
        "notes": [{"id": str(n.id), "body": n.body, "created_at": n.created_at.isoformat() if n.created_at else None} for n in notes],
        "saved_searches": [{"id": str(s.id), "name": s.name, "city": s.city} for s in saved_searches],
    }
