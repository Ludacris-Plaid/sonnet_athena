"""
Twilio Voice webhook handlers: lets a client call a real phone number and
have an actual spoken conversation with Athena.

Uses Twilio's own built-in speech recognition (<Gather input="speech">)
rather than streaming raw audio to our own STT — this is simpler, has lower
latency, and is what Twilio Voice is designed for. Athena's replies are
synthesized via our TTS provider and played back with <Play>.

Setup (once you have a Twilio account):
  1. Buy/configure a phone number in the Twilio console.
  2. Set its "A call comes in" webhook to:
       POST {PUBLIC_BASE_URL}/voice/telephony/incoming-call
  3. Set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER /
     PUBLIC_BASE_URL in .env. PUBLIC_BASE_URL must be a real, internet-
     reachable URL (e.g. via ngrok in dev, your real domain in production) —
     Twilio fetches your TwiML and audio URLs from the public internet.

Note: this identifies the calling org/user by matching TWILIO_PHONE_NUMBER
to a specific org in a real multi-tenant deployment you'd look up the
org/user by the "To" number Twilio provides (each org would need its own
Twilio number, or a shared number + IVR to select the right agent). Left as
TODO with a single-tenant default for clarity.
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.core.config import settings
from app.core.database import get_db
from app.models.org import Organization, User
from app.models.message import Message, Channel, MessageDirection
from app.services.voice_conversation_service import generate_spoken_reply
from app.services.voice_service import get_tts_provider, save_audio_to_cache
from app.services.compliance_alert_service import raise_compliance_alert

router = APIRouter(prefix="/voice/telephony", tags=["voice-telephony"])


def _resolve_default_org_and_user(db: Session) -> tuple[Organization | None, User | None]:
    """
    TODO: replace with real lookup by the Twilio "To" number once each org
    has its own provisioned number. For now, routes calls to the first admin
    user, so the single-tenant / demo case works out of the box.
    """
    user = db.query(User).filter(User.is_admin == True).first()  # noqa: E712
    if not user:
        return None, None
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    return org, user


@router.post("/incoming-call")
async def incoming_call(request: Request, db: Session = Depends(get_db)):
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{settings.PUBLIC_BASE_URL}/voice/telephony/handle-speech",
        method="POST",
        speech_timeout="auto",
    )
    gather.say("Hi, this is Athena. How can I help you today?", voice="Polly.Joanna")
    response.append(gather)
    response.say("Sorry, I didn't catch that. Goodbye for now.")
    return Response(content=str(response), media_type="application/xml")


@router.post("/handle-speech")
async def handle_speech(
    SpeechResult: str = Form(""),
    CallSid: str = Form(""),
    From: str = Form(""),
    db: Session = Depends(get_db),
):
    response = VoiceResponse()

    org, user = _resolve_default_org_and_user(db)
    if not org or not user:
        response.say("Athena isn't fully set up yet. Please try again later.")
        return Response(content=str(response), media_type="application/xml")

    if not SpeechResult:
        response.say("I didn't catch that — could you say it again?")
        gather = Gather(
            input="speech",
            action=f"{settings.PUBLIC_BASE_URL}/voice/telephony/handle-speech",
            method="POST",
            speech_timeout="auto",
        )
        response.append(gather)
        return Response(content=str(response), media_type="application/xml")

    inbound = Message(
        org_id=org.id, user_id=user.id, channel=Channel.VOICE,
        direction=MessageDirection.INBOUND, from_address=From, body=SpeechResult,
    )
    db.add(inbound)
    db.commit()

    reply = generate_spoken_reply(db, str(org.id), SpeechResult, caller_context="client")
    reply_text = reply["reply_text"]

    outbound = Message(
        org_id=org.id, user_id=user.id, channel=Channel.VOICE,
        direction=MessageDirection.OUTBOUND, to_address=From, body=reply_text, sent_autonomously=True,
        compliance_flagged=reply["compliance_flagged"], compliance_notes=reply["compliance_notes"],
    )
    db.add(outbound)
    db.commit()

    if outbound.compliance_flagged:
        raise_compliance_alert(db, str(org.id), str(user.id), outbound)

    try:
        audio_bytes = get_tts_provider(db, str(org.id)).synthesize(reply_text)
        audio_id = save_audio_to_cache(audio_bytes)
        response.play(f"{settings.PUBLIC_BASE_URL}/voice/audio/{audio_id}")
    except RuntimeError:
        # TTS not configured — fall back to Twilio's built-in voice so the call still works
        response.say(reply_text, voice="Polly.Joanna")

    gather = Gather(
        input="speech",
        action=f"{settings.PUBLIC_BASE_URL}/voice/telephony/handle-speech",
        method="POST",
        speech_timeout="auto",
    )
    response.append(gather)
    return Response(content=str(response), media_type="application/xml")
