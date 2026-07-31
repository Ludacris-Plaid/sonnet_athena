"""
"Quick communication" with a listing agent — drafts a message, and
records a sent copy as an outbound Message (channel=email, no client_id
since the listing agent isn't a CRM contact) so it shows up in the
regular Inbox/timeline history, not a disconnected one-off action.
"""
from sqlalchemy.orm import Session

from app.models.property import Property
from app.models.message import Message, Channel, MessageDirection
from app.services.llm_service import llm_service
from app.services.compliance_service import keyword_risk_summary
from app.prompts.agent_outreach import SYSTEM_PROMPT, build_prompt

PURPOSE_PRESETS = {
    "request_showing": "Request a showing for a buyer client, asking about available times.",
    "ask_question": "Ask a clarifying question about the listing (condition, inclusions, timeline).",
    "submit_interest": "Let the listing agent know a buyer client is interested and may submit an offer soon.",
}


def draft_message_to_agent(db: Session, property_id: str, purpose: str, extra_context: str | None = None) -> dict:
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise ValueError("Property not found")
    if not prop.listing_agent_email and not prop.listing_agent_phone:
        raise ValueError("No listing agent contact info on file for this property.")

    purpose_text = PURPOSE_PRESETS.get(purpose, purpose)
    property_data = {
        "address": prop.address, "city": prop.city, "state": prop.state, "price": prop.price,
        "listing_agent_name": prop.listing_agent_name, "listing_brokerage": prop.listing_brokerage,
    }
    prompt = build_prompt(property_data, purpose_text, extra_context)
    response = llm_service.complete(SYSTEM_PROMPT, prompt, temperature=0.5, max_tokens=350)
    draft = response.text.strip()

    risk = keyword_risk_summary(draft)  # same informational compliance check as inbox drafts

    return {
        "draft": draft,
        "to_name": prop.listing_agent_name,
        "to_email": prop.listing_agent_email,
        "to_phone": prop.listing_agent_phone,
        "compliance_risk": risk["risk"],
        "compliance_flags": risk["flags"],
    }


def send_message_to_agent(db: Session, org_id: str, user_id: str, property_id: str, body: str) -> Message:
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise ValueError("Property not found")

    risk = keyword_risk_summary(body)
    msg = Message(
        org_id=org_id, user_id=user_id, client_id=None,
        channel=Channel.EMAIL, direction=MessageDirection.OUTBOUND,
        to_address=prop.listing_agent_email, subject=f"Re: {prop.address}", body=body,
        compliance_flagged=risk["risk"] != "low",
        compliance_notes=", ".join(f["phrase"] for f in risk["flags"]) if risk["flags"] else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
