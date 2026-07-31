"""
Chat now runs through athena_agent_service — real tool-calling access to
the whole platform (see that file's docstring for why the old fixed-intent
orchestrator wasn't enough: it could only answer questions with an
explicit if/elif branch). command_parser_service's fast path still runs
first for deterministic slash-style commands, since that's cheaper and
more predictable than a full tool-calling round trip for things like
"assign client X to Y."
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.command_parser_service import try_parse_command
from app.services.command_execution_service import execute_command
from app.services.athena_agent_service import run_athena_chat
from app.services import conversation_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = conversation_service.get_or_create_active_conversation(db, str(user.org_id), str(user.id), context="chat")

    command = try_parse_command(payload.message)
    if command:
        conversation_service.add_message(db, str(conv.id), "user", payload.message)
        result_text = execute_command(db, str(user.org_id), command)
        conversation_service.add_message(db, str(conv.id), "assistant", result_text)
        return {"reply": result_text, "conversation_id": str(conv.id)}

    result = run_athena_chat(db, user, str(conv.id), payload.message)
    return {**result, "conversation_id": str(conv.id)}
