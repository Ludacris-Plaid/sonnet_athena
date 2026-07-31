from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.opportunity_service import score_opportunities

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("")
def get_opportunities(
    city: str,
    min_score: float = 50,
    limit: int = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return score_opportunities(db, str(user.org_id), city, min_score=min_score, limit=limit)
