from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.negotiation_service import suggest_negotiation_strategy

router = APIRouter(prefix="/negotiation", tags=["negotiation"])


@router.post("/{property_id}")
def negotiation_strategy(property_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return suggest_negotiation_strategy(db, property_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
