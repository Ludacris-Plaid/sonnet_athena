from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.org import User
from app.services import memory_browse_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def list_memories(category: str | None = None, client_id: str | None = None, search: str | None = None, user: User = Depends(get_current_user)):
    return memory_browse_service.list_memories(str(user.org_id), category, client_id, search)


@router.get("/categories")
def get_categories(user: User = Depends(get_current_user)):
    return memory_browse_service.get_category_taxonomy()


@router.get("/{memory_id}")
def get_memory(memory_id: str, user: User = Depends(get_current_user)):
    memory = memory_browse_service.get_memory(memory_id)
    if not memory or memory.get("org_id") != str(user.org_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, user: User = Depends(get_current_user)):
    memory = memory_browse_service.get_memory(memory_id)
    if not memory or memory.get("org_id") != str(user.org_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    memory_browse_service.delete_memory(memory_id)
    return {"ok": True}
