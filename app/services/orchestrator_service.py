"""
Chat orchestrator: classifies the user's message intent, routes it to the
right existing service, and falls back to a grounded general-purpose reply
using recalled memory when no specific tool applies.

This is intentionally a plain-Python router rather than a heavyweight agent
framework — it's a thin dispatch table, which is easier to test, debug, and
extend than a black-box multi-agent chain. If you want to swap in CrewAI or
LangGraph later, this module is the seam: replace `route_message`'s body
with a Crew/graph invocation and keep the same function signature so
routes_chat.py doesn't need to change.
"""
import re

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.property import Property
from app.services.llm_service import llm_service
from app.services.memory_service import recall
from app.services.opportunity_service import score_opportunities
from app.services.hermes_agent_service import delegate_task, is_hermes_available, HermesNotConfiguredError
from app.services.command_parser_service import try_parse_command
from app.services.command_execution_service import execute_command
from app.prompts.chat_router import SYSTEM_PROMPT, INTENTS
from app.prompts.athena_persona import ATHENA_CORE_PERSONA

GENERAL_SYSTEM_PROMPT = f"""{ATHENA_CORE_PERSONA}

Answer using only the context provided below — if you don't have enough \
information, say so plainly and suggest what the agent could ask or check \
instead, rather than guessing."""


def classify_intent(message: str) -> str:
    response = llm_service.complete(SYSTEM_PROMPT, message, temperature=0.0, max_tokens=10)
    label = response.text.strip().lower()
    return label if label in INTENTS else "general"


def route_message(db: Session, org_id: str, user_id: str, message: str) -> dict:
    # Fast path: deterministic command parsing before spending an LLM call
    # on intent classification. Inspired by Meridian Company OS's
    # command-driven ops chat pattern — see command_parser_service.py.
    command = try_parse_command(message)
    if command:
        result_text = execute_command(db, org_id, command)
        return _reply(f"command:{command.command}", result_text)

    intent = classify_intent(message)

    if intent == "list_clients":
        clients = db.query(Client).filter(Client.org_id == org_id).all()
        if not clients:
            return _reply(intent, "You don't have any clients yet. Add one from the Clients tab.")
        lines = [f"- {c.name} ({c.client_type}), budget up to ${c.budget_max:,.0f}" if c.budget_max else f"- {c.name} ({c.client_type})" for c in clients]
        return _reply(intent, "Here are your active clients:\n" + "\n".join(lines))

    if intent == "list_properties":
        props = db.query(Property).filter(Property.org_id == org_id, Property.status == "active").limit(10).all()
        if not props:
            return _reply(intent, "No properties yet — pull some listings from the Properties tab first.")
        lines = [f"- {p.address}: ${p.price:,.0f}" for p in props if p.price]
        return _reply(intent, "Here are some active listings:\n" + "\n".join(lines))

    if intent == "opportunities":
        city = _extract_city(message)
        if not city:
            return _reply(intent, "Which city should I check for opportunities?")
        opps = score_opportunities(db, org_id, city, min_score=55, limit=5)
        if not opps:
            return _reply(intent, f"No standout opportunities in {city} right now based on current listings.")
        lines = [f"- {o['address']}: ${o['price']:,.0f}, opportunity score {o['opportunity_score']}/100" for o in opps]
        return _reply(intent, f"Top opportunities in {city}:\n" + "\n".join(lines))

    if intent in ("run_cma", "neighborhood", "investment", "negotiation"):
        return _reply(
            intent,
            f"That looks like a {intent.replace('_', ' ')} request — open the relevant property or "
            f"neighborhood page and use the dedicated tool there for a grounded, data-backed answer "
            f"(chat alone doesn't have the specific property selected yet).",
        )

    if intent == "deep_research":
        if not is_hermes_available():
            return _reply(
                intent,
                "This looks like a deep research task — the kind I'd hand off to Hermes for sustained, "
                "multi-step work. Hermes isn't connected yet (set HERMES_ENABLED and the connection "
                "details in .env). For now I can take a faster pass at it directly — want me to?",
            )
        try:
            result = delegate_task(
                prompt=message,
                system_context="You are being consulted by Athena, a real estate AI assistant, on behalf "
                "of a licensed realtor. Provide thorough, well-researched analysis.",
            )
            return _reply(intent, result.text)
        except HermesNotConfiguredError as e:
            return _reply(intent, str(e))
        except Exception as e:  # noqa: BLE001 — surface a clean message, not a raw 500, for a flaky external service
            return _reply(intent, f"Hermes hit an error handling that: {e}. You can try again, or ask me directly for a faster (less thorough) answer.")

    # General fallback: use recalled memory as context, answer conversationally
    context = recall(org_id, message, top_k=5)
    context_block = "\n".join(f"- {c['text']}" for c in context) or "No relevant memory found."
    prompt = f"CONTEXT:\n{context_block}\n\nMESSAGE:\n{message}"
    response = llm_service.complete(GENERAL_SYSTEM_PROMPT, prompt, temperature=0.6, max_tokens=550)
    return _reply("general", response.text)


def _reply(intent: str, text: str) -> dict:
    return {"intent": intent, "reply": text}


def _extract_city(message: str) -> str | None:
    # Very simple heuristic: look for "in <City>" pattern. Swap for a proper
    # NER pass or structured client-side city selector for production use.
    match = re.search(r"\bin ([A-Z][a-zA-Z\s]+?)(?:[.,!?]|$)", message)
    return match.group(1).strip() if match else None
