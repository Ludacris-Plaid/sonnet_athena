"""
Prompts for generating and reworking realtor documents.

Scope note, deliberately enforced by what's NOT here: this generates
marketing materials, guides, checklists, disclosure DRAFTS, and deal-points
WORKSHEETS — never purchase agreements, listing agreements, or other
binding contracts. Binding real estate contracts need jurisdiction-specific,
board-approved standard forms (many US states and Canadian provinces
mandate a specific form by regulation) and a lawyer's or broker's review;
an AI-generated "contract" presented as ready to sign is a genuine
liability, not a convenience — and drafting binding legal terms for someone
else can edge into unauthorized practice of law depending on jurisdiction.
If a person asks for a purchase agreement or listing agreement, the answer
is the deal-points worksheet types below (internal prep only, explicitly
not a contract) — never a full contract type.
"""

DEAL_POINTS_CAVEAT = """
IMPORTANT: this is an internal deal-points WORKSHEET, not a contract. Open \
the document with a bold header stating clearly that this is not a binding \
agreement, was not prepared on any state/board-approved form, and must be \
used only to hand these terms to a broker or transaction coordinator who \
will prepare the actual agreement on the correct legally-required form for \
the jurisdiction. Never format this to resemble a signable contract — no \
signature lines, no "Buyer/Seller agrees to..." binding language. Present \
terms as a plain labeled list instead (e.g. "Offer price: [X]", "Financing \
contingency: [X] days")."""

GENERATION_SYSTEM_PROMPT = """You are Athena, drafting a real estate business \
document for a licensed realtor. Write clearly and professionally. Never invent \
specific facts (prices, dates, legal terms, property details) — use placeholder \
brackets like [PROPERTY ADDRESS] or [CLOSING DATE] for anything you don't have. \
Never use language that could imply a preference or limitation based on race, \
color, religion, sex, disability, familial status, national origin, or other \
protected characteristics."""

DISCLOSURE_DRAFT_CAVEAT = """
IMPORTANT: this document type is a disclosure DRAFT — a non-binding starting \
point only. Explicitly state at the top of the document, in bold or as a clear \
header, that this draft must be reviewed by the brokerage's legal counsel and \
adapted to the specific state/provincial mandated disclosure form before use, \
and that it is not a substitute for a jurisdiction's official disclosure form."""

DOC_TYPE_INSTRUCTIONS = {
    "marketing_flyer": "Write copy for a one-page property marketing flyer: a headline, 4-6 highlight bullet points, and a closing call to action.",
    "listing_description": "Write a detailed, professional listing description for internal/marketing use, 200-300 words.",
    "disclosure_draft": "Draft a general seller property disclosure document covering common categories (known defects, systems/appliances, environmental hazards, past repairs). Use placeholder brackets for anything property-specific." + DISCLOSURE_DRAFT_CAVEAT,
    "buyer_guide": "Write a short buyer's guide (500-700 words) explaining the home-buying process at a high level, in plain language, for a first-time buyer client.",
    "seller_guide": "Write a short seller's guide (500-700 words) explaining the home-selling process at a high level, in plain language.",
    "email_newsletter": "Write a monthly newsletter email for the realtor's client list: a market update paragraph (with placeholder brackets for actual figures), a featured listing section, and a closing personal note.",
    "transaction_checklist": "Write a step-by-step transaction checklist from accepted offer to closing, as a clear numbered list with brief descriptions of each step.",
    "cover_letter": "Write a template cover letter a buyer can personalize to submit with an offer, warm and genuine in tone, with placeholder brackets for buyer-specific details.",
    "listing_agreement_prep": "Create a deal-points worksheet capturing the terms to be discussed for a listing agreement: property address, list price, commission split, listing period (start/end dates), marketing terms, and any special conditions. Use placeholder brackets for anything not provided." + DEAL_POINTS_CAVEAT,
    "purchase_offer_prep": "Create a deal-points worksheet capturing the terms of a purchase offer: offer price, earnest money amount, financing type and contingency period, inspection contingency period, closing date, included/excluded items, and any special terms. Use placeholder brackets for anything not provided." + DEAL_POINTS_CAVEAT,
}


def build_generation_prompt(doc_type: str, instructions: str | None, context: str | None) -> str:
    base_instructions = DOC_TYPE_INSTRUCTIONS.get(doc_type, "Write a professional real estate business document.")
    extra = f"\n\nADDITIONAL INSTRUCTIONS FROM THE AGENT:\n{instructions}" if instructions else ""
    ctx = f"\n\nRELEVANT CONTEXT:\n{context}" if context else ""
    return f"DOCUMENT TYPE INSTRUCTIONS:\n{base_instructions}{extra}{ctx}"


REWORK_SYSTEM_PROMPT = """You are Athena, revising a real estate document. You are \
given the current text and a list of fair housing compliance flags raised against \
it. Rewrite the document to resolve every flagged issue while preserving the \
original intent, structure, and any facts that weren't flagged. If additional \
agent instructions are given, apply those too. Return ONLY the revised document \
text — no preamble, no explanation of what you changed."""


def build_rework_prompt(current_content: str, flags: list[dict], extra_instructions: str | None) -> str:
    flags_block = "\n".join(f"- \"{f.get('phrase', f.get('protected_class', ''))}\": {f.get('explanation', f.get('note', ''))}" for f in flags) or "None — general polish requested."
    extra = f"\n\nADDITIONAL AGENT INSTRUCTIONS:\n{extra_instructions}" if extra_instructions else ""
    return f"""CURRENT DOCUMENT:
{current_content}

FLAGGED ISSUES TO RESOLVE:
{flags_block}{extra}

Return the revised document."""
