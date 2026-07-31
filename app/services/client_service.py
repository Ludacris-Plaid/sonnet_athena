"""
Core CRM operations: contact CRUD, pipeline stage transitions, tagging,
notes, tasks, saved searches, and duplicate detection/merge.
"""
import difflib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client, ClientNote, ClientActivityLog, ClientTask, SavedSearch, PIPELINE_STAGES, LEAD_TEMPERATURES


def create_client(db: Session, org_id: str, owning_user_id: str, **fields) -> Client:
    client = Client(org_id=org_id, owning_user_id=owning_user_id, **fields)
    db.add(client)
    db.commit()
    db.refresh(client)
    _log_activity(db, client.id, owning_user_id, "created", {})
    return client


def get_client(db: Session, client_id: str) -> Client | None:
    return db.query(Client).filter(Client.id == client_id).first()


def list_clients(
    db: Session,
    org_id: str,
    search: str | None = None,
    pipeline_stage: str | None = None,
    lead_temperature: str | None = None,
    tag: str | None = None,
) -> list[Client]:
    query = db.query(Client).filter(Client.org_id == org_id)
    if search:
        like = f"%{search}%"
        query = query.filter((Client.name.ilike(like)) | (Client.email.ilike(like)) | (Client.phone.ilike(like)))
    if pipeline_stage:
        query = query.filter(Client.pipeline_stage == pipeline_stage)
    if lead_temperature:
        query = query.filter(Client.lead_temperature == lead_temperature)
    clients = query.order_by(Client.updated_at.desc()).all()
    if tag:
        clients = [c for c in clients if tag in (c.tags or [])]
    return clients


def update_client(db: Session, client_id: str, updates: dict) -> Client:
    client = get_client(db, client_id)
    if not client:
        raise ValueError("Client not found")
    for key, value in updates.items():
        if value is not None and hasattr(client, key):
            setattr(client, key, value)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def change_pipeline_stage(db: Session, client_id: str, user_id: str, new_stage: str) -> Client:
    if new_stage not in PIPELINE_STAGES:
        raise ValueError(f"Invalid pipeline stage: {new_stage}. Valid: {PIPELINE_STAGES}")
    client = get_client(db, client_id)
    if not client:
        raise ValueError("Client not found")

    old_stage = client.pipeline_stage
    client.pipeline_stage = new_stage
    db.add(client)
    db.commit()
    db.refresh(client)

    _log_activity(db, client.id, user_id, "stage_change", {"old_stage": old_stage, "new_stage": new_stage})
    return client


def add_tag(db: Session, client_id: str, user_id: str, tag: str) -> Client:
    client = get_client(db, client_id)
    if not client:
        raise ValueError("Client not found")
    tags = list(client.tags or [])
    if tag not in tags:
        tags.append(tag)
        client.tags = tags
        db.add(client)
        db.commit()
        db.refresh(client)
        _log_activity(db, client.id, user_id, "tag_added", {"tag": tag})
    return client


def remove_tag(db: Session, client_id: str, tag: str) -> Client:
    client = get_client(db, client_id)
    if not client:
        raise ValueError("Client not found")
    tags = [t for t in (client.tags or []) if t != tag]
    client.tags = tags
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _log_activity(db: Session, client_id, user_id: str | None, event_type: str, detail: dict) -> None:
    entry = ClientActivityLog(client_id=client_id, user_id=user_id, event_type=event_type, detail=detail)
    db.add(entry)
    db.commit()


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def add_note(db: Session, client_id: str, user_id: str, body: str) -> ClientNote:
    note = ClientNote(client_id=client_id, user_id=user_id, body=body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_notes(db: Session, client_id: str) -> list[ClientNote]:
    return db.query(ClientNote).filter(ClientNote.client_id == client_id).order_by(ClientNote.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def create_task(db: Session, client_id: str, user_id: str, title: str, due_at=None) -> ClientTask:
    task = ClientTask(client_id=client_id, user_id=user_id, title=title, due_at=due_at)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, task_id: str) -> ClientTask:
    task = db.query(ClientTask).filter(ClientTask.id == task_id).first()
    if not task:
        raise ValueError("Task not found")
    task.is_completed = True
    task.completed_at = datetime.now(timezone.utc)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session, client_id: str, include_completed: bool = False) -> list[ClientTask]:
    query = db.query(ClientTask).filter(ClientTask.client_id == client_id)
    if not include_completed:
        query = query.filter(ClientTask.is_completed == False)  # noqa: E712
    return query.order_by(ClientTask.due_at.asc().nullslast()).all()


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------

def create_saved_search(db: Session, client_id: str, **fields) -> SavedSearch:
    search = SavedSearch(client_id=client_id, **fields)
    db.add(search)
    db.commit()
    db.refresh(search)
    return search


def list_saved_searches(db: Session, client_id: str) -> list[SavedSearch]:
    return db.query(SavedSearch).filter(SavedSearch.client_id == client_id, SavedSearch.is_active == True).all()  # noqa: E712


# ---------------------------------------------------------------------------
# Duplicate detection + merge
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def find_potential_duplicates(db: Session, org_id: str, threshold: float = 0.82) -> list[dict]:
    """
    Fuzzy-matches on name (and exact-matches email/phone when present) to
    surface likely duplicate pairs for the agent to review — never
    auto-merges. Returns pairs sorted by confidence, highest first.
    """
    clients = db.query(Client).filter(Client.org_id == org_id).all()
    pairs = []
    for i, a in enumerate(clients):
        for b in clients[i + 1:]:
            score = _similarity(a.name, b.name)
            if a.email and b.email and a.email.lower() == b.email.lower():
                score = max(score, 0.99)
            if a.phone and b.phone and a.phone == b.phone:
                score = max(score, 0.95)
            if score >= threshold:
                pairs.append({"client_a": a, "client_b": b, "confidence": round(score, 2)})
    pairs.sort(key=lambda p: p["confidence"], reverse=True)
    return pairs


def touch_last_contacted(db: Session, client_id: str) -> None:
    """
    Call this whenever a Message (inbound or outbound) is linked to a
    client. This is what makes the "timeline fills itself" claim actually
    true rather than aspirational — last_contacted_at (which drives
    lead_scoring_service's staleness scoring and the stale-lead alert)
    updates automatically from real communication, no manual step needed.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client.last_contacted_at = datetime.now(timezone.utc)
        db.add(client)
        db.commit()


def merge_clients(db: Session, primary_id: str, duplicate_id: str, user_id: str) -> Client:
    """
    Merges `duplicate` into `primary`: fills any blank fields on primary
    from the duplicate, reassigns the duplicate's notes/tasks/saved
    searches/messages to primary, then deletes the duplicate record.
    """
    primary = get_client(db, primary_id)
    duplicate = get_client(db, duplicate_id)
    if not primary or not duplicate:
        raise ValueError("Both clients must exist to merge")
    if primary.id == duplicate.id:
        raise ValueError("Cannot merge a client with itself")

    for field in ("email", "phone", "budget_max", "preferred_city", "lead_source", "deal_value"):
        if getattr(primary, field) is None and getattr(duplicate, field) is not None:
            setattr(primary, field, getattr(duplicate, field))
    primary.tags = list(set((primary.tags or []) + (duplicate.tags or [])))

    from app.models.message import Message
    db.query(Message).filter(Message.client_id == duplicate.id).update({"client_id": primary.id})
    db.query(ClientNote).filter(ClientNote.client_id == duplicate.id).update({"client_id": primary.id})
    db.query(ClientTask).filter(ClientTask.client_id == duplicate.id).update({"client_id": primary.id})
    db.query(SavedSearch).filter(SavedSearch.client_id == duplicate.id).update({"client_id": primary.id})

    db.add(primary)
    db.delete(duplicate)
    db.commit()
    db.refresh(primary)

    _log_activity(db, primary.id, user_id, "merged", {"merged_client_id": str(duplicate_id)})
    return primary
