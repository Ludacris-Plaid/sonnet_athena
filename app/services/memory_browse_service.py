"""
Browse/filter/delete for the Memories tab — separate from memory_service.py
(which handles remember()/recall() for the chat/voice context-injection
path) since browsing is a different access pattern: list everything
matching filters, not semantic top-K search.
"""
from app.memory.vector_store import vector_store

# Taxonomy shown in the Memories tab — label/color/icon per category, kept
# server-side so the frontend never has to guess or hardcode a mapping
# that could drift from what the backend actually writes. See
# memory_service.classify_memory_category() for how "preference" vs "fact"
# get decided, and client_ai_service.py for where "insight" gets written.
MEMORY_CATEGORIES = {
    "preference": {"label": "Preference", "color": "gold", "icon": "⭐"},
    "fact": {"label": "Fact", "color": "olive", "icon": "📌"},
    "insight": {"label": "Insight", "color": "violet", "icon": "💡"},
}


def get_category_taxonomy() -> dict:
    return MEMORY_CATEGORIES


def list_memories(org_id: str, category: str | None = None, client_id: str | None = None, search: str | None = None) -> list[dict]:
    def _filter(meta: dict) -> bool:
        if meta.get("org_id") != org_id:
            return False
        if category and meta.get("category") != category:
            return False
        if client_id and meta.get("client_id") != client_id:
            return False
        if search and search.lower() not in meta.get("text", "").lower():
            return False
        return True

    results = vector_store.list_all(filter_fn=_filter)
    results.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return results


def get_memory(memory_id: str) -> dict | None:
    return vector_store.get(memory_id)


def delete_memory(memory_id: str) -> bool:
    return vector_store.delete(memory_id)
