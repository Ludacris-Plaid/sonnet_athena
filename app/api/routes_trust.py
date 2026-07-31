from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.trust import TrustScore
from app.services.trust_gamification_service import get_gamification_summary

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/me")
def my_trust_scores(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Raw per-action trust scores — kept for backward compatibility with existing callers."""
    scores = db.query(TrustScore).filter(TrustScore.user_id == user.id).all()
    return scores


@router.get("/gamification")
def gamification_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Everything the reworked Trust tab needs: overall level, badges (earned + locked), hints, per-action breakdown."""
    return get_gamification_summary(db, str(user.id))
