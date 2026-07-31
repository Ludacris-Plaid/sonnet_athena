from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.daily_briefing_service import get_daily_briefing

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("")
def briefing(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_daily_briefing(db, str(user.org_id), str(user.id), user.full_name)
