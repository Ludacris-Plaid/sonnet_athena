"""
Athena's semantic memory: facts and preferences about clients and users,
scoped per-org so tenants never leak into each other's memory.

To swap in the real mem0 SDK later:
  pip install mem0ai
  from mem0 import Memory
  m = Memory()
  m.add(text, user_id=..., metadata=...)
  m.search(query, user_id=...)
Then re-point the functions below at `m` instead of `vector_store`.
"""
import re

from app.memory.vector_store import vector_store

# Keyword heuristic for auto-classifying captured statements as a stated
# preference vs. a general fact — cheap, no extra LLM call, run on every
# remember() call so the Memories tab actually shows real variety instead
# of everything landing in one bucket. Not perfect NLP, but the failure
# mode is mild (a preference filed as a fact still shows up in search).
_PREFERENCE_PATTERNS = re.compile(
    r"\b(wants?|prefers?|looking for|needs?|would like|budget|must have|deal[\s-]?breaker)\b",
    re.IGNORECASE,
)


def classify_memory_category(text: str) -> str:
    return "preference" if _PREFERENCE_PATTERNS.search(text) else "fact"


def remember(org_id: str, text: str, category: str | None = None, client_id: str | None = None) -> str:
    """
    Store a memory. If category isn't given explicitly, it's inferred from
    the text via classify_memory_category() — pass category="insight"
    explicitly for Athena's own derived observations (see
    client_ai_service.py), which shouldn't go through the fact/preference
    heuristic since they're not captured statements.
    """
    resolved_category = category or classify_memory_category(text)
    return vector_store.add(
        text,
        {"org_id": org_id, "category": resolved_category, "client_id": client_id},
    )


def recall(org_id: str, query: str, client_id: str | None = None, top_k: int = 5) -> list[dict]:
    """Semantic recall, scoped to org (and optionally a specific client)."""

    def _filter(meta: dict) -> bool:
        if meta.get("org_id") != org_id:
            return False
        if client_id and meta.get("client_id") != client_id:
            return False
        return True

    return vector_store.search(query, top_k=top_k, filter_fn=_filter)
