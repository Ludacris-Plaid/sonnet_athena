"""
Grounds Athena's answers about the PLATFORM ITSELF (not client/property
data) in the real docs content — so "how do I connect my calendar" gets an
answer sourced from docs_content.py, not a hallucinated guess.
"""
from app.docs_content import search_sections, get_all_sections
from app.services.llm_service import llm_service
from app.prompts.athena_persona import ATHENA_CORE_PERSONA

SYSTEM_PROMPT = f"""{ATHENA_CORE_PERSONA}

Right now you're answering a question about how the RealtyAI platform
itself works, grounded strictly in the documentation excerpts given below
— never invent a feature, button, or behavior that isn't in the docs. If
the docs don't cover what's being asked, say so plainly and suggest
checking the full Docs tab or Settings."""


def answer_docs_question(question: str) -> dict:
    relevant = search_sections(question)
    if not relevant:
        relevant = get_all_sections()[:3]  # fall back to a few general sections rather than nothing

    context = "\n\n".join(
        f"### {s['title']} ({s['category']})\n{s['summary']}\n" + "\n".join(f"- {step}" for step in s["walkthrough"])
        for s in relevant[:5]
    )
    prompt = f"DOCUMENTATION EXCERPTS:\n{context}\n\nQUESTION: {question}\n\nAnswer using only the excerpts above."
    response = llm_service.complete(SYSTEM_PROMPT, prompt, temperature=0.4, max_tokens=400)
    return {"answer": response.text.strip(), "sources": [{"id": s["id"], "title": s["title"]} for s in relevant[:5]]}
