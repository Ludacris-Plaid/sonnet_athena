"""
Self-contained compliance logic for the standalone MCP server — deliberately
not importing from the main `app` package, so this server can be deployed
and run independently (e.g. as a separate process registered with Claude
Desktop) without needing the full RealtyAI backend installed alongside it.

Uses DeepSeek directly for the LLM contextual pass, since that's the
platform's primary model — set DEEPSEEK_API_KEY in the environment.
"""
import json
import os
import re

import httpx

from compliance_data import FLAGGED_PHRASES, DISCLOSURE_REFERENCE, AML_OVERVIEW

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

DISCLAIMER = (
    "This is an automated first-pass check, not legal advice. Confirm with your "
    "brokerage's compliance officer or the relevant state/provincial regulator "
    "before relying on it."
)

SYSTEM_PROMPT = """You are a fair housing compliance reviewer for real estate listing \
text. You check for language that could violate the US federal Fair Housing Act \
(race, color, religion, sex, disability, familial status, national origin) or \
Canadian provincial human rights codes (which commonly add sexual orientation, \
gender identity, age, marital/family status, and sometimes source of income).

A deterministic keyword scan has already run; its hits are given to you as context. \
Catch phrasing the scan would miss, and correct any false positives — ordinary \
property description language (square footage, "walk-in closet", proximity to \
landmarks used neutrally) is never a violation.

Respond with ONLY valid JSON: {"flags": [{"phrase": "...", "protected_class": "...", \
"explanation": "...", "severity": "high"|"caution"}], "overall_risk": "high"|"caution"|"low"}
"""


def keyword_scan(text: str) -> list[dict]:
    lowered = text.lower()
    hits = []
    for category, phrases in FLAGGED_PHRASES.items():
        for entry in phrases:
            phrase = entry["phrase"]
            if phrase.startswith("no [") or phrase.endswith("]"):
                continue
            if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
                hits.append({"phrase": phrase, "category": category, "severity": entry["severity"], "note": entry["note"]})
    return hits


def _call_deepseek(system_prompt: str, user_prompt: str) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not set in environment")
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.0,
        "max_tokens": 600,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def screen_listing_text(text: str) -> dict:
    hits = keyword_scan(text)
    hits_block = "\n".join(f"- \"{h['phrase']}\" ({h['category']}, {h['severity']}): {h['note']}" for h in hits) or "None."
    user_prompt = f"LISTING TEXT:\n{text}\n\nKEYWORD SCAN HITS:\n{hits_block}\n\nRespond with the JSON format specified."

    try:
        raw = _call_deepseek(SYSTEM_PROMPT, user_prompt)
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        llm_result = json.loads(cleaned)
    except (RuntimeError, json.JSONDecodeError, httpx.HTTPError, KeyError):
        # Falls back to the deterministic scan alone if the LLM call fails or
        # isn't configured — the tool still returns a useful result either way.
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
            "note": f"No reference data for '{jurisdiction}' yet. Available: {available}.",
            "disclaimer": DISCLAIMER,
        }
    return {"jurisdiction": jurisdiction, "items": items, "disclaimer": DISCLAIMER}


def get_aml_overview(country: str) -> dict:
    country = country.upper().strip()
    data = AML_OVERVIEW.get(country)
    if not data:
        return {"country": country, "error": "Only 'US' and 'CA' are covered.", "disclaimer": DISCLAIMER}
    return {"country": country, **data, "disclaimer": DISCLAIMER}


def get_protected_classes(country: str) -> dict:
    from compliance_data import US_FEDERAL_PROTECTED_CLASSES, CANADA_COMMON_PROTECTED_GROUNDS

    country = country.upper().strip()
    if country == "US":
        return {"country": "US", "protected_classes": US_FEDERAL_PROTECTED_CLASSES,
                "note": "Federal Fair Housing Act classes. States/cities frequently add more (e.g. source of income, sexual orientation) — check local law.",
                "disclaimer": DISCLAIMER}
    if country == "CA":
        return {"country": "CA", "protected_grounds": CANADA_COMMON_PROTECTED_GROUNDS,
                "note": "Representative list common across provinces — housing discrimination is governed by PROVINCIAL human rights codes, which vary. Check the specific province.",
                "disclaimer": DISCLAIMER}
    return {"error": "Only 'US' and 'CA' are covered.", "disclaimer": DISCLAIMER}
