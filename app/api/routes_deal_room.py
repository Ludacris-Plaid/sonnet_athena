"""
Deal Room — the aggregated per-client view Athena suggested adding.
Rebuilt from the version found in the uploaded server code, which queried
messages/properties/documents scoped to the whole ORG instead of the
specific client — meaning every deal room would have shown identical,
unrelated data regardless of which client you opened. Fixed to use real
per-client relations throughout; see deal_room_service.py's docstring.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.deal_room_service import get_deal_room

router = APIRouter(prefix="/deal-room", tags=["deal_room"])


@router.get("/{client_id}")
def deal_room(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return get_deal_room(db, str(client_id), str(user.org_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
