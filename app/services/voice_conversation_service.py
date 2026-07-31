"""
Full voice turn: audio in -> transcript -> routed reply (spoken persona) ->
audio out. Every turn is logged as a Message (channel=voice) so voice
conversations feed the same memory and history as email/SMS — Athena
"remembering" what you told her on a call is what makes the friend framing
actually work, not just the voice itself.
"""
from sqlalchemy.orm import Session

from app.models.message import Message, Channel, MessageDirection
from app.services.voice_service import get_stt_provider, get_tts_provider, save_audio_to_cache
from app.services.llm_service import llm_service
from app.services.memory_service import recall, remember
from app.services.compliance_service import keyword_risk_summary
from app.services.compliance_alert_service import raise_compliance_alert
from app.services import client_service
from app.prompts.voice_persona import AGENT_SYSTEM_PROMPT, CLIENT_SYSTEM_PROMPT, build_context_prompt

# Spoken instead of the actual reply whenever a high-severity fair housing
# flag is caught. Deliberately generic — no attempt to "fix" the flagged
# content on the fly and speak a patched version, since that risks
# confidently saying something subtly still wrong. Defer to a human instead.
COMPLIANCE_FALLBACK_REPLY = (
    "That's something I want to double check before I say more on it — "
    "let me have your agent follow up with you directly on that."
)


def handle_voice_turn(
    db: Session,
    org_id: str,
    user_id: str,
    audio_bytes: bytes,
    filename: str = "audio.webm",
    client_id: str | None = None,
) -> dict:
    transcript = get_stt_provider(db, org_id).transcribe(audio_bytes, filename=filename)

    inbound = Message(
        org_id=org_id,
        user_id=user_id,
        client_id=client_id,
        channel=Channel.VOICE,
        direction=MessageDirection.INBOUND,
        body=transcript,
    )
    db.add(inbound)
    db.commit()
    db.refresh(inbound)

    reply = generate_spoken_reply(db, org_id, transcript, client_id=client_id)

    outbound = Message(
        org_id=org_id,
        user_id=user_id,
        client_id=client_id,
        channel=Channel.VOICE,
        direction=MessageDirection.OUTBOUND,
        body=reply["reply_text"],
        sent_autonomously=True,  # voice is inherently real-time; there's no draft-approval step mid-conversation
        compliance_flagged=reply["compliance_flagged"],
        compliance_notes=reply["compliance_notes"],
    )
    db.add(outbound)
    db.commit()
    db.refresh(outbound)

    if outbound.compliance_flagged:
        raise_compliance_alert(db, org_id, user_id, outbound)

    if client_id:
        client_service.touch_last_contacted(db, client_id)

    audio_reply = get_tts_provider(db, org_id).synthesize(reply["reply_text"])
    audio_id = save_audio_to_cache(audio_reply)

    return {
        "transcript": transcript,
        "reply_text": reply["reply_text"],
        "audio_id": audio_id,
        "inbound_message_id": inbound.id,
        "outbound_message_id": outbound.id,
        "compliance_flagged": reply["compliance_flagged"],
    }


def generate_spoken_reply(db: Session, org_id: str, message: str, client_id: str | None = None, caller_context: str = "agent") -> dict:
    """
    Text-only variant of a voice turn — used by both handle_voice_turn and
    the Twilio webhook (which gets transcription for free from Twilio's own
    <Gather input="speech">, so it skips straight to this).

    Returns {"reply_text": str, "compliance_flagged": bool, "compliance_notes": str|None}.

    Enforces a HARD gate on fair housing risk before returning — unlike the
    inbox flow, there's no human approval step between this and the client
    hearing it, so a flagged reply is replaced with a safe deflection rather
    than just logged as a warning.
    """
    context = recall(org_id, message, client_id=client_id, top_k=5)
    context_block = "\n".join(f"- {c['text']}" for c in context) or "Nothing specific remembered yet."

    prompt = build_context_prompt(context_block, message)
    system_prompt = AGENT_SYSTEM_PROMPT if caller_context == "agent" else CLIENT_SYSTEM_PROMPT
    response = llm_service.complete(system_prompt, prompt, temperature=0.6, max_tokens=200)
    reply_text = response.text.strip()

    risk = keyword_risk_summary(reply_text)
    compliance_flagged = risk["risk"] != "low"
    compliance_notes = ", ".join(f["phrase"] for f in risk["flags"]) if risk["flags"] else None

    if risk["risk"] == "high":
        reply_text = COMPLIANCE_FALLBACK_REPLY
        # Keep compliance_flagged=True and the original notes even though we
        # swapped the reply — the flag should still surface to the agent for
        # review, since it points at something the LLM said that needs a
        # human look regardless of what was actually spoken.

    # Let notable facts from the conversation feed back into memory, the same
    # way a real assistant would remember what you told them.
    if len(message) > 20:
        remember(org_id, message, client_id=client_id)  # category auto-classified — see memory_service.classify_memory_category

    return {"reply_text": reply_text, "compliance_flagged": compliance_flagged, "compliance_notes": compliance_notes}
