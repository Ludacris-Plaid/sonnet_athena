from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.neighborhood import Neighborhood
from app.schemas.neighborhood import NeighborhoodOut
from app.services.analysis_service import score_neighborhood

router = APIRouter(prefix="/neighborhood", tags=["neighborhood"])


@router.get("", response_model=list[NeighborhoodOut])
def list_neighborhoods(city: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Neighborhood)
    if city:
        query = query.filter(Neighborhood.city == city)
    return query.all()


@router.post("/{neighborhood_id}/score")
def score(neighborhood_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return score_neighborhood(db, neighborhood_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
