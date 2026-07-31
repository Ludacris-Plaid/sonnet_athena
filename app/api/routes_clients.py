"""
The CRM: full client CRUD, pipeline management, notes, tasks, saved
searches, duplicate detection/merge, AI features, and lead scoring.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.client import PIPELINE_STAGES, LEAD_TEMPERATURES
from app.schemas.client import (
    ClientCreate, ClientUpdate, ClientOut, StageChangeRequest, TagRequest,
    NoteCreate, NoteOut, TaskCreate, TaskOut, SavedSearchCreate, SavedSearchOut, MergeRequest,
)
from app.services import client_service, lead_scoring_service, client_ai_service
from app.services.client_timeline_service import get_client_timeline
from app.services.alert_service import evaluate_stale_lead_alerts

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/meta")
def get_meta(user: User = Depends(get_current_user)):
    """Pipeline stages and temperature options, for the frontend to render selects/board columns."""
    return {"pipeline_stages": PIPELINE_STAGES, "lead_temperatures": LEAD_TEMPERATURES}


@router.get("", response_model=list[ClientOut])
def list_clients(
    search: str | None = None,
    pipeline_stage: str | None = None,
    lead_temperature: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return client_service.list_clients(db, str(user.org_id), search, pipeline_stage, lead_temperature, tag)


@router.post("", response_model=ClientOut)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.create_client(db, str(user.org_id), str(user.id), **payload.model_dump())


@router.get("/duplicates")
def get_duplicates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pairs = client_service.find_potential_duplicates(db, str(user.org_id))
    return [
        {
            "confidence": p["confidence"],
            "client_a": {"id": str(p["client_a"].id), "name": p["client_a"].name, "email": p["client_a"].email},
            "client_b": {"id": str(p["client_b"].id), "name": p["client_b"].name, "email": p["client_b"].email},
        }
        for p in pairs
    ]


@router.post("/merge", response_model=ClientOut)
def merge(payload: MergeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.merge_clients(db, payload.primary_id, payload.duplicate_id, str(user.id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/check-stale-leads")
def check_stale_leads(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """On-demand trigger — wire to a scheduled job in production for true zero-setup behavior."""
    events = evaluate_stale_lead_alerts(db, str(user.org_id))
    return {"new_alerts": len(events)}


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = client_service.get_client(db, str(client_id))
    if not client or str(client.org_id) != str(user.org_id):
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: UUID, payload: ClientUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.update_client(db, str(client_id), payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{client_id}/stage", response_model=ClientOut)
def change_stage(client_id: UUID, payload: StageChangeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.change_pipeline_stage(db, str(client_id), str(user.id), payload.new_stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{client_id}/tags", response_model=ClientOut)
def add_tag(client_id: UUID, payload: TagRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.add_tag(db, str(client_id), str(user.id), payload.tag)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{client_id}/tags/{tag}", response_model=ClientOut)
def remove_tag(client_id: UUID, tag: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.remove_tag(db, str(client_id), tag)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{client_id}/timeline")
def timeline(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_client_timeline(db, str(client_id))


# --- Notes ---

@router.post("/{client_id}/notes", response_model=NoteOut)
def add_note(client_id: UUID, payload: NoteCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.add_note(db, str(client_id), str(user.id), payload.body)


@router.get("/{client_id}/notes", response_model=list[NoteOut])
def list_notes(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.list_notes(db, str(client_id))


# --- Tasks ---

@router.post("/{client_id}/tasks", response_model=TaskOut)
def create_task(client_id: UUID, payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.create_task(db, str(client_id), str(user.id), payload.title, payload.due_at)


@router.get("/{client_id}/tasks", response_model=list[TaskOut])
def list_tasks(client_id: UUID, include_completed: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.list_tasks(db, str(client_id), include_completed)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return client_service.complete_task(db, str(task_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Saved searches ---

@router.post("/{client_id}/saved-searches", response_model=SavedSearchOut)
def create_saved_search(client_id: UUID, payload: SavedSearchCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.create_saved_search(db, str(client_id), **payload.model_dump())


@router.get("/{client_id}/saved-searches", response_model=list[SavedSearchOut])
def list_saved_searches(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return client_service.list_saved_searches(db, str(client_id))


# --- Lead scoring ---

@router.post("/{client_id}/recompute-score", response_model=ClientOut)
def recompute_score(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = client_service.get_client(db, str(client_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return lead_scoring_service.recompute_and_save(db, client)


# --- AI differentiators ---

@router.post("/{client_id}/ai/brief")
def relationship_brief(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return {"brief": client_ai_service.generate_relationship_brief(db, str(client_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{client_id}/ai/next-action")
def next_action(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return {"suggestion": client_ai_service.suggest_next_action(db, str(client_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{client_id}/ai/suggest-tags")
def suggest_tags(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return {"suggested_tags": client_ai_service.suggest_tags(db, str(client_id))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
