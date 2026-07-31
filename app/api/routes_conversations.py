"""
Conversation history management — list/search, resume an old one, and the
one explicit reset action. See conversation_service.py's module docstring
for the core rule this enforces: nothing resets unless the user calls
POST /conversations/new themselves.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.conversation import ConversationOut, ConversationMessageOut
from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(context: str = "chat", search: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return conversation_service.list_conversations(db, str(user.id), context, search)


@router.get("/active", response_model=ConversationOut)
def get_active(context: str = "chat", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The conversation that should load by default — created automatically if none exists yet."""
    conv = conversation_service.get_or_create_active_conversation(db, str(user.org_id), str(user.id), context)
    return conv


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageOut])
def get_messages(conversation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return conversation_service.get_conversation_messages(db, str(conversation_id))


@router.post("/new", response_model=ConversationOut)
def new_conversation(context: str = "chat", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The explicit reset — starts a fresh conversation. The old one is deactivated, never deleted."""
    return conversation_service.start_new_conversation(db, str(user.org_id), str(user.id), context)


@router.post("/{conversation_id}/activate", response_model=ConversationOut)
def activate(conversation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Resume an old conversation — makes it the active one again."""
    try:
        return conversation_service.activate_conversation(db, str(user.id), str(conversation_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
