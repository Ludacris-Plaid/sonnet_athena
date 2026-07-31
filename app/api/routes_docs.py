from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.org import User
from app.docs_content import get_all_sections, search_sections, get_section
from app.services.docs_service import answer_docs_question


router = APIRouter(prefix="/docs", tags=["docs"])


@router.get("")
def list_docs(user: User = Depends(get_current_user)):
    return get_all_sections()


@router.get("/search")
def search_docs(q: str, user: User = Depends(get_current_user)):
    return search_sections(q) if q else get_all_sections()


@router.get("/{section_id}")
def get_doc(section_id: str, user: User = Depends(get_current_user)):
    return get_section(section_id)


@router.post("/ask")
def ask_docs(payload: dict, user: User = Depends(get_current_user)):
    return answer_docs_question(payload.get("question", ""))
