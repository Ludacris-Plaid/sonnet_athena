"""
Explicit delegation to Hermes Agent — a dedicated endpoint (separate from
the /chat auto-routing) for a clear "Go Deep" action in the UI, since these
calls can take minutes and deserve their own loading state rather than
looking like a stuck chat message.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.hermes_agent_service import delegate_task, is_hermes_available, HermesNotConfiguredError
from app.services.approvals_service import get_pending_approvals

router = APIRouter(prefix="/agent", tags=["agent"])


class DelegateRequest(BaseModel):
    task: str
    context: str | None = None


@router.get("/hermes-status")
def hermes_status(user: User = Depends(get_current_user)):
    return {"available": is_hermes_available()}


@router.post("/delegate")
def delegate(payload: DelegateRequest, user: User = Depends(get_current_user)):
    try:
        result = delegate_task(payload.task, payload.context)
        return {"result": result.text}
    except HermesNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Hermes Agent error: {e}")


@router.get("/approvals")
def approvals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Everything currently waiting on a human decision, in one list."""
    return get_pending_approvals(db, str(user.org_id))
