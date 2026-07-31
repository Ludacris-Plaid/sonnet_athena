"""Text optimization endpoint — no agent loop, no tools, no conversation history. The "lightning bolt" prompt optimizer in Inbox and Chat."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.api.deps import get_current_user
from app.models.org import User
from app.services.llm_service import llm_service

router = APIRouter(prefix="/optimize", tags=["optimize"])


class OptimizeRequest(BaseModel):
    text: str
    tone: str = "professional real estate"


@router.post("")
def optimize(payload: OptimizeRequest, user: User = Depends(get_current_user)):
    prompt = f"""Rewrite the following message with a {payload.tone} tone. Fix any spelling, grammar, or awkward phrasing. Make it clear and natural. Return ONLY the rewritten text, no explanation, no markdown, no quotes:

{payload.text}"""
    result = llm_service.complete("You are a writing assistant for real estate professionals. Improve clarity and tone without changing the actual meaning or adding claims that weren't in the original.", prompt, max_tokens=500, temperature=0.4)
    return {"original": payload.text, "optimized": result.text.strip()}
