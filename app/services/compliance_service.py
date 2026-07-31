"""
Fair housing language screening (US + Canada), disclosure reference lookup,
and AML overview — a compliance-assistance layer, not a compliance
guarantee. Every result explicitly carries the caveat that this doesn't
replace review by the brokerage's compliance officer or legal counsel.

Screening is two-pass: a fast deterministic keyword scan first (cheap,
no LLM call, catches the obvious cases), then an LLM contextual pass that
sees the keyword hits as context and can both catch subtler phrasing and
correct keyword false positives. This mirrors why real compliance review
in practice uses both a checklist AND a human reviewer — neither alone is
reliable.
"""
import json
import re

from app.services.compliance_data import FLAGGED_PHRASES, DISCLOSURE_REFERENCE, AML_OVERVIEW
from app.services.llm_service import llm_service
from app.prompts import compliance as compliance_prompts

DISCLAIMER = (
    "This is an automated first-pass check, not legal advice. Confirm with your "
    "brokerage's compliance officer or the relevant state/provincial regulator "
    "before relying on it."
)


def keyword_scan(text: str) -> list[dict]:
    lowered = text.lower()
    hits = []
    for category, phrases in FLAGGED_PHRASES.items():
        for entry in phrases:
            phrase = entry["phrase"]
            if phrase.startswith("no [") or phrase.endswith("]"):
                continue  # placeholder patterns, not literal strings to match
            if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
                hits.append({"phrase": phrase, "category": category, "severity": entry["severity"], "note": entry["note"]})
    return hits


def keyword_risk_summary(text: str) -> dict:
    """
    Fast, no-LLM-call risk check — for latency-sensitive call sites (bulk
    property ingestion, the real-time voice gate) where the full two-pass
    screen_listing_text() would be too slow or too expensive to run on
    every item. Returns {"risk": "high"|"caution"|"low", "flags": [...]}.
    """
    hits = keyword_scan(text)
    if not hits:
        return {"risk": "low", "flags": []}
    risk = "high" if any(h["severity"] == "high" for h in hits) else "caution"
    return {"risk": risk, "flags": hits}


def screen_listing_text(text: str) -> dict:
    hits = keyword_scan(text)

    prompt = compliance_prompts.build_user_prompt(text, hits)
    response = llm_service.complete(compliance_prompts.SYSTEM_PROMPT, prompt, temperature=0.0, max_tokens=600)

    try:
        cleaned = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        llm_result = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        # If the model didn't return clean JSON, fall back to the deterministic
        # scan alone rather than silently dropping results.
        llm_result = {
            "flags": [{"phrase": h["phrase"], "protected_class": h["category"], "explanation": h["note"], "severity": h["severity"]} for h in hits],
            "overall_risk": "caution" if hits else "low",
        }

    return {
        "flags": llm_result.get("flags", []),
        "overall_risk": llm_result.get("overall_risk", "low"),
        "keyword_scan_hit_count": len(hits),
        "disclaimer": DISCLAIMER,
    }


def get_disclosure_reference(jurisdiction: str) -> dict:
    jurisdiction = jurisdiction.upper().strip()
    items = DISCLOSURE_REFERENCE.get(jurisdiction)
    if not items:
        available = ", ".join(sorted(DISCLOSURE_REFERENCE.keys()))
        return {
            "jurisdiction": jurisdiction,
            "items": [],
            "note": f"No reference data for '{jurisdiction}' yet. Available: {available}. "
                    f"This list is illustrative and non-exhaustive regardless.",
            "disclaimer": DISCLAIMER,
        }
    return {"jurisdiction": jurisdiction, "items": items, "disclaimer": DISCLAIMER}


def get_aml_overview(country: str) -> dict:
    country = country.upper().strip()
    data = AML_OVERVIEW.get(country)
    if not data:
        return {"country": country, "error": "Only 'US' and 'CA' are covered.", "disclaimer": DISCLAIMER}
    return {"country": country, **data, "disclaimer": DISCLAIMER}
