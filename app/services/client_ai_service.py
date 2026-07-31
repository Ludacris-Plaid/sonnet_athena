"""
The AI-powered CRM differentiators: relationship briefs, next-best-action
suggestions, and smart tag suggestions — all grounded in real timeline
data (never fabricated), all going through the fast DeepSeek path since
these are interactive, on-demand requests, not background jobs.
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.services.llm_service import llm_service
from app.services.client_timeline_service import get_client_timeline
from app.services.memory_service import remember
from app.prompts.client_ai import (
    SYSTEM_PROMPT_BRIEF, SYSTEM_PROMPT_NEXT_ACTION, SYSTEM_PROMPT_TAGS,
    build_brief_prompt, build_next_action_prompt, build_tags_prompt,
)


def _client_to_dict(client: Client) -> dict:
    return {
        "name": client.name,
        "client_type": client.client_type,
        "budget_max": client.budget_max,
        "preferred_city": client.preferred_city,
        "pipeline_stage": client.pipeline_stage,
        "pre_approved": client.pre_approved,
        "timeline": client.timeline,
        "lead_source": client.lead_source,
        "tags": client.tags,
        "last_contacted_at": client.last_contacted_at.isoformat() if client.last_contacted_at else None,
    }


def generate_relationship_brief(db: Session, client_id: str) -> str:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")
    timeline = get_client_timeline(db, client_id, limit=30)
    prompt = build_brief_prompt(_client_to_dict(client), timeline)
    response = llm_service.complete(SYSTEM_PROMPT_BRIEF, prompt, temperature=0.5, max_tokens=450)
    return response.text.strip()


def suggest_next_action(db: Session, client_id: str) -> str:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")
    timeline = get_client_timeline(db, client_id, limit=20)
    prompt = build_next_action_prompt(_client_to_dict(client), timeline)
    response = llm_service.complete(SYSTEM_PROMPT_NEXT_ACTION, prompt, temperature=0.4, max_tokens=350)
    suggestion = response.text.strip()

    # Athena's own derived judgment call becomes a searchable memory, not
    # just a one-off UI response — this is what makes the Memories tab show
    # real "insight" entries rather than just captured facts/preferences.
    remember(str(client.org_id), f"Next action for {client.name}: {suggestion}", category="insight", client_id=str(client.id))

    return suggestion


def suggest_tags(db: Session, client_id: str) -> list[str]:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")
    prompt = build_tags_prompt(_client_to_dict(client))
    response = llm_service.complete(SYSTEM_PROMPT_TAGS, prompt, temperature=0.3, max_tokens=60)
    suggested = [t.strip() for t in response.text.split(",") if t.strip()]
    existing = set(client.tags or [])
    return [t for t in suggested if t not in existing][:3]
