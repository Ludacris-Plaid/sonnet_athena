"""
The Search tab's brain: queries everything in one call — clients,
properties, documents, memories, past conversations, compliance
reference data, and (optionally) the live web — and returns categorized
results. Each category is independently try/excepted so one slow or
failing source (e.g. the web search API being down) never breaks the
whole search.
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.property import Property
from app.models.document import Document
from app.services import memory_browse_service, conversation_service
from app.services.web_search_service import search_web
from app.services.compliance_data import DISCLOSURE_REFERENCE, AML_OVERVIEW


def search_everything(db: Session, org_id: str, user_id: str, query: str, include_web: bool = True) -> dict:
    results = {
        "clients": _search_clients(db, org_id, query),
        "properties": _search_properties(db, org_id, query),
        "documents": _search_documents(db, org_id, query),
        "memories": _search_memories(org_id, query),
        "conversations": _search_conversations(db, user_id, query),
        "compliance": _search_compliance(query),
        "web": search_web(f"{query} real estate", db=db, org_id=org_id) if include_web else [],
    }
    results["total_count"] = sum(len(v) for v in results.values())
    return results


def _search_clients(db: Session, org_id: str, query: str) -> list[dict]:
    try:
        like = f"%{query}%"
        clients = (
            db.query(Client)
            .filter(Client.org_id == org_id)
            .filter((Client.name.ilike(like)) | (Client.email.ilike(like)) | (Client.phone.ilike(like)) | (Client.preferred_city.ilike(like)))
            .limit(10)
            .all()
        )
        return [{"id": str(c.id), "title": c.name, "subtitle": f"{c.client_type} · {c.pipeline_stage}", "url": f"/app/client-detail.html?id={c.id}"} for c in clients]
    except Exception:  # noqa: BLE001
        return []


def _search_properties(db: Session, org_id: str, query: str) -> list[dict]:
    try:
        like = f"%{query}%"
        props = (
            db.query(Property)
            .filter(Property.org_id == org_id)
            .filter((Property.address.ilike(like)) | (Property.city.ilike(like)) | (Property.mls_number.ilike(like)) | (Property.description.ilike(like)))
            .limit(10)
            .all()
        )
        return [{"id": str(p.id), "title": p.address, "subtitle": f"${p.price:,.0f}" if p.price else p.city, "url": "/app/properties.html"} for p in props]
    except Exception:  # noqa: BLE001
        return []


def _search_documents(db: Session, org_id: str, query: str) -> list[dict]:
    try:
        like = f"%{query}%"
        docs = (
            db.query(Document)
            .filter(Document.org_id == org_id)
            .filter((Document.title.ilike(like)) | (Document.content.ilike(like)))
            .limit(10)
            .all()
        )
        return [{"id": str(d.id), "title": d.title, "subtitle": d.doc_type.value, "url": "/app/documents.html"} for d in docs]
    except Exception:  # noqa: BLE001
        return []


def _search_memories(org_id: str, query: str) -> list[dict]:
    try:
        memories = memory_browse_service.list_memories(org_id, search=query)[:10]
        return [{"id": m["id"], "title": m["text"][:80], "subtitle": m.get("category", "fact"), "url": "/app/memories.html"} for m in memories]
    except Exception:  # noqa: BLE001
        return []


def _search_conversations(db: Session, user_id: str, query: str) -> list[dict]:
    try:
        convs = conversation_service.list_conversations(db, user_id, context="chat", search=query)[:10]
        return [{"id": str(c.id), "title": c.title or "Untitled conversation", "subtitle": c.last_message_at.strftime("%b %d, %Y"), "url": f"/app/settings.html?conversation={c.id}"} for c in convs]
    except Exception:  # noqa: BLE001
        return []


def _search_compliance(query: str) -> list[dict]:
    """Searches the static disclosure-reference and AML-overview data — not a DB query, just a text match over reference content."""
    results = []
    q = query.lower()
    for jurisdiction, items in DISCLOSURE_REFERENCE.items():
        for item in items:
            if q in item.lower() or q in jurisdiction.lower():
                results.append({"id": jurisdiction, "title": item[:80], "subtitle": f"Disclosure reference — {jurisdiction}", "url": "/app/compliance.html"})
    for country, data in AML_OVERVIEW.items():
        if q in data.get("summary", "").lower() or q in country.lower():
            results.append({"id": country, "title": data["summary"][:80], "subtitle": f"AML overview — {country}", "url": "/app/compliance.html"})
    return results[:10]


def synthesize_results(query: str, results: dict) -> str:
    """
    An opt-in AI summary of what search turned up — deliberately NOT run
    automatically on every keystroke (search already runs live as you
    type; re-summarizing on every debounce would be slow and wasteful).
    This is for the "just tell me what this means" button.
    """
    from app.services.llm_service import llm_service
    from app.prompts.athena_persona import ATHENA_CORE_PERSONA

    system_prompt = f"""{ATHENA_CORE_PERSONA}

Right now you're summarizing search results for this agent — grounded
strictly in the titles/subtitles given below, never inventing anything
beyond them. 2-4 sentences: what's actually here, and if something stands
out as worth their attention first, say so plainly."""

    lines = []
    for category, items in results.items():
        if category in ("total_count",) or not items:
            continue
        for item in items[:5]:
            title = item.get("title") or item.get("summary", "")
            lines.append(f"[{category}] {title}")

    if not lines:
        return "Nothing came up for that search — try a different term, or broaden it."

    prompt = f'QUERY: "{query}"\n\nRESULTS FOUND:\n' + "\n".join(lines) + "\n\nSummarize this."
    response = llm_service.complete(system_prompt, prompt, temperature=0.5, max_tokens=300)
    return response.text.strip()
