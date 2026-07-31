"""
Aggregates everything scattered across clients/tasks/calendar/alerts into
one morning-briefing payload. Deterministic aggregation (fast, always
correct) plus one LLM pass for the "AI Insights" section, where judgment
matters more than raw numbers — matches the pattern used throughout this
codebase (compute first, narrate second).
"""
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.message import Message, MessageDirection
from app.services import calendar_service
from app.services.client_service import list_tasks
from app.services.lead_scoring_service import get_stale_clients
from app.services.approvals_service import get_pending_approvals
from app.services.llm_service import llm_service
from app.prompts.daily_briefing import SYSTEM_PROMPT, build_prompt


def get_daily_briefing(db: Session, org_id: str, user_id: str, user_name: str) -> dict:
    clients = db.query(Client).filter(Client.org_id == org_id, Client.status == "active").all()
    stale = get_stale_clients(db, org_id, days=14)
    hot = [c for c in clients if c.lead_temperature == "hot"]
    todays_events = calendar_service.get_todays_events(db, org_id, user_id)
    approvals = get_pending_approvals(db, org_id)
    pipeline_value = sum(c.deal_value or 0 for c in clients if c.pipeline_stage not in ("closed_won", "closed_lost"))

    overdue_tasks = []
    for c in clients:
        for t in list_tasks(db, str(c.id)):
            if t.due_at and t.due_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                overdue_tasks.append({"client_name": c.name, "title": t.title})

    recent_messages = (
        db.query(Message)
        .filter(Message.org_id == org_id, Message.direction == MessageDirection.INBOUND)
        .order_by(Message.created_at.desc())
        .limit(5)
        .all()
    )

    context = {
        "total_clients": len(clients),
        "stale_lead_names": ", ".join(c.name for c in stale[:8]) or "none",
        "hot_lead_names": ", ".join(c.name for c in hot[:8]) or "none",
        "todays_event_titles": ", ".join(e.title for e in todays_events) or "nothing scheduled",
        "overdue_task_titles": ", ".join(f"{t['title']} ({t['client_name']})" for t in overdue_tasks[:8]) or "none",
        "alert_headlines": ", ".join(a["summary"] for a in approvals[:8]) or "none",
        "pipeline_value": pipeline_value,
    }

    ai_insights = _generate_insights(context)

    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")

    return {
        "greeting": f"{greeting}, {user_name.split(' ')[0]}",
        "date": datetime.now().strftime("%A, %B %d, %Y"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_clients": len(clients),
            "new_clients_7d": len([c for c in clients if (datetime.now(timezone.utc) - c.created_at.replace(tzinfo=timezone.utc)).days <= 7]),
            "stale_leads": len(stale),
            "hot_leads": len(hot),
            "todays_events": len(todays_events),
            "overdue_tasks": len(overdue_tasks),
            "pending_approvals": len(approvals),
            "high_priority_approvals": len([a for a in approvals if a["priority"] == "high"]),
            "pipeline_value": pipeline_value,
        },
        "ai_insights": ai_insights,
        "todays_events": [
            {"id": str(e.id), "title": e.title, "start_at": e.start_at.isoformat(), "event_type": e.event_type}
            for e in todays_events
        ],
        "priorities": approvals[:10],
        "stale_leads": [{"id": str(c.id), "name": c.name} for c in stale[:10]],
        "hot_leads": [{"id": str(c.id), "name": c.name, "budget_max": c.budget_max} for c in hot[:10]],
        "overdue_tasks": overdue_tasks[:10],
        "recent_messages": [
            {
                "id": str(m.id),
                "channel": m.channel.value,
                "from_address": m.from_address or "unknown",
                "subject": m.subject,
                "preview": (m.body or "")[:80],
                "compliance_flagged": m.compliance_flagged,
                "created_at": m.created_at.isoformat(),
            }
            for m in recent_messages
        ],
    }


def _generate_insights(context: dict) -> list[str]:
    """
    Returns a list of standalone insight strings (rendered as individual
    numbered cards in the UI, matching the reference design — never a
    single paragraph blob). Parses the LLM's "1. ... / 2. ..." format;
    falls back to a single explanatory line if the LLM call fails or
    doesn't follow the format, so the briefing never shows a raw error or
    an empty section.
    """
    try:
        prompt = build_prompt(context)
        response = llm_service.complete(SYSTEM_PROMPT, prompt, temperature=0.6, max_tokens=350)
        raw = response.text.strip()
    except Exception as e:  # noqa: BLE001 — a briefing should never fail to load just because the LLM call hiccuped
        return [f"AI insights are unavailable right now ({e}) — everything else on this page is unaffected."]

    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    parsed = []
    for line in lines:
        cleaned = re.sub(r"^\d+\.\s*", "", line).strip()
        if cleaned:
            parsed.append(cleaned)

    return parsed if parsed else [raw]  # if the model didn't number its lines, show the whole thing as one card rather than drop it
