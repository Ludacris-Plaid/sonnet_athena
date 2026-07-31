"""
Merges Messages (real communications — email/SMS/voice, already flowing
through the platform), ClientNotes (manual notes), and ClientActivityLog
(stage changes, tags, merges) into one chronological timeline.

This is the "fills itself" differentiator: competing CRMs need manual
logging or an expensive dialer/power-dial integration to populate a
contact's communication history. Here it's free — every message already
lands in the same Message table the unified inbox uses, so the timeline
is just a query, not a separate system to maintain.
"""
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.client import ClientNote, ClientActivityLog


def get_client_timeline(db: Session, client_id: str, limit: int = 100) -> list[dict]:
    events = []

    messages = db.query(Message).filter(Message.client_id == client_id).order_by(Message.created_at.desc()).limit(limit).all()
    for m in messages:
        events.append({
            "type": "message",
            "channel": m.channel.value,
            "direction": m.direction.value,
            "summary": m.body[:200],
            "compliance_flagged": m.compliance_flagged,
            "timestamp": m.created_at,
        })

    notes = db.query(ClientNote).filter(ClientNote.client_id == client_id).order_by(ClientNote.created_at.desc()).limit(limit).all()
    for n in notes:
        events.append({"type": "note", "summary": n.body, "timestamp": n.created_at})

    activity = db.query(ClientActivityLog).filter(ClientActivityLog.client_id == client_id).order_by(ClientActivityLog.created_at.desc()).limit(limit).all()
    for a in activity:
        events.append({"type": a.event_type, "summary": _describe_activity(a), "timestamp": a.created_at})

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events[:limit]


def _describe_activity(entry: ClientActivityLog) -> str:
    detail = entry.detail or {}
    if entry.event_type == "stage_change":
        return f"Moved from {detail.get('old_stage')} to {detail.get('new_stage')}"
    if entry.event_type == "tag_added":
        return f"Tagged: {detail.get('tag')}"
    if entry.event_type == "merged":
        return "Merged with a duplicate record"
    if entry.event_type == "created":
        return "Client created"
    return entry.event_type
