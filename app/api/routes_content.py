from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.content import ContentGenerateRequest, ContentItemOut
from app.services.content_generation_service import generate_content, get_available_content_types

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/types")
def list_content_types(user: User = Depends(get_current_user)):
    return get_available_content_types()


@router.post("/generate", response_model=list[ContentItemOut])
def generate(payload: ContentGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return generate_content(db, payload.property_id, payload.content_types)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
