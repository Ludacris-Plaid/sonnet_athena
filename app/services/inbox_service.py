"""
Unified inbox draft generation: for any inbound message (email/SMS/etc.),
generate several tone-varied reply drafts and let the trust ladder decide
whether the user must approve, or Athena can send autonomously.
"""
from sqlalchemy.orm import Session

from app.models.message import Message, MessageDirection, Channel
from app.models.trust import ActionType
from app.services.llm_service import llm_service
from app.services.memory_service import recall
from app.services import trust_service
from app.services.compliance_service import keyword_risk_summary
from app.services.compliance_alert_service import raise_compliance_alert
from app.services import client_service

TONE_INSTRUCTIONS = {
    "professional": "Polished, businesslike, no slang.",
    "warm": "Friendly and personable, still professional.",
    "brief": "As short as possible while still complete. 2-3 sentences max.",
    "urgent": "Conveys time-sensitivity and a clear next step, without being pushy.",
}

SYSTEM_PROMPT = """You are Athena, a real estate assistant drafting a reply on \
behalf of a licensed realtor. Use the client context provided to personalize the \
reply. Never invent facts about the client, pricing, or availability that are not \
given to you. Sign off as the realtor, not as an AI."""


def generate_drafts(db: Session, message: Message, tones: list[str]) -> list[dict]:
    context = recall(str(message.org_id), message.body, client_id=str(message.client_id) if message.client_id else None)
    context_block = "\n".join(f"- {c['text']}" for c in context) or "No prior context available."

    drafts = []
    for tone in tones:
        tone_note = TONE_INSTRUCTIONS.get(tone, "")
        prompt = f"""INBOUND MESSAGE ({message.channel.value}):
{message.body}

KNOWN CLIENT CONTEXT:
{context_block}

TONE FOR THIS DRAFT: {tone_note}

Write a reply to the inbound message above."""
        response = llm_service.complete(SYSTEM_PROMPT, prompt, temperature=0.6, max_tokens=350)
        # Fast keyword-only check, surfaced to the human reviewer as a
        # warning — this doesn't block anything here, since a human still
        # chooses which draft to send. It's an early heads-up, not a gate.
        risk = keyword_risk_summary(response.text)
        drafts.append({"tone": tone, "body": response.text, "compliance_risk": risk["risk"], "compliance_flags": risk["flags"]})

    message.draft_replies = drafts
    db.add(message)
    db.commit()
    return drafts


def resolve_action_type_for_channel(channel: str) -> ActionType:
    return ActionType.SEND_EMAIL if channel == "email" else ActionType.SEND_SMS


def send_new_message(
    db: Session,
    org_id: str,
    user_id: str,
    channel: Channel,
    to_address: str,
    body: str,
    client_id: str | None = None,
    subject: str | None = None,
) -> Message:
    """
    Sends a message that ISN'T a reply to a specific pending inbound one —
    proactive outreach ("just checking in"), starting a new thread, or
    following up after a thread's already been answered. This is what
    makes the Inbox composer behave like a real chat box (always able to
    type and send) instead of only working when there's literally
    something waiting to be replied to.
    """
    action_type = resolve_action_type_for_channel(channel)
    risk = keyword_risk_summary(body)

    outbound = Message(
        org_id=org_id,
        user_id=user_id,
        client_id=client_id,
        channel=channel,
        direction=MessageDirection.OUTBOUND,
        from_address=None,
        to_address=to_address,
        subject=subject,
        body=body,
        was_edited_before_send=False,
        compliance_flagged=risk["risk"] != "low",
        compliance_notes=", ".join(f["phrase"] for f in risk["flags"]) if risk["flags"] else None,
    )
    db.add(outbound)
    db.commit()
    db.refresh(outbound)

    if outbound.compliance_flagged:
        raise_compliance_alert(db, org_id, user_id, outbound)

    if client_id:
        client_service.touch_last_contacted(db, client_id)

    trust_service.record_outcome(db, user_id, action_type, "sent_unedited", related_message_id=str(outbound.id))
    db.commit()
    return outbound


def send_reply(
    db: Session,
    inbound_message: Message,
    chosen_body: str,
    user_id: str,
    was_edited: bool,
    force_autonomous_check: bool = True,
) -> Message:
    """
    Records the outbound reply and feeds the outcome back into the trust ladder.
    In a real deployment, this is also where the actual email/SMS provider
    (Gmail API / Twilio) send call happens.
    """
    action_type = resolve_action_type_for_channel(inbound_message.channel.value)

    # Check again at send time, not just at draft time — the human may have
    # hand-edited the body into something the original draft never had.
    # Still informational only here: a human explicitly chose to send this.
    risk = keyword_risk_summary(chosen_body)

    outbound = Message(
        org_id=inbound_message.org_id,
        user_id=user_id,
        client_id=inbound_message.client_id,
        channel=inbound_message.channel,
        direction=MessageDirection.OUTBOUND,
        from_address=inbound_message.to_address,
        to_address=inbound_message.from_address,
        subject=f"Re: {inbound_message.subject}" if inbound_message.subject else None,
        body=chosen_body,
        was_edited_before_send=was_edited,
        compliance_flagged=risk["risk"] != "low",
        compliance_notes=", ".join(f["phrase"] for f in risk["flags"]) if risk["flags"] else None,
    )
    db.add(outbound)
    db.commit()
    db.refresh(outbound)

    if outbound.compliance_flagged:
        raise_compliance_alert(db, str(inbound_message.org_id), user_id, outbound)

    if outbound.client_id:
        client_service.touch_last_contacted(db, str(outbound.client_id))

    # Clear the now-stale drafts on the inbound message — it's been
    # answered, so re-loading the inbox later shouldn't show drafts for a
    # question that's already resolved.
    inbound_message.draft_replies = None
    db.add(inbound_message)

    outcome = "edited" if was_edited else "sent_unedited"
    trust_service.record_outcome(db, user_id, action_type, outcome, related_message_id=str(outbound.id))

    db.commit()
    return outbound
