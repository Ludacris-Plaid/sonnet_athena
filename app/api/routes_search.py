from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.universal_search_service import search_everything, synthesize_results

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(q: str, include_web: bool = True, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not q or len(q.strip()) < 2:
        return {"total_count": 0, "clients": [], "properties": [], "documents": [], "memories": [], "conversations": [], "compliance": [], "web": []}
    return search_everything(db, str(user.org_id), str(user.id), q.strip(), include_web)


@router.post("/summarize")
def summarize(payload: dict, user: User = Depends(get_current_user)):
    return {"summary": synthesize_results(payload.get("query", ""), payload.get("results", {}))}
