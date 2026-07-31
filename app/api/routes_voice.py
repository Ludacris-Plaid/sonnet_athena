"""
In-app voice: browser records audio, posts it here, gets back a transcript,
Athena's spoken-style reply text, and an audio_id to fetch/play.

Persists into the SAME conversation thread as text chat (see
conversation_service.py) — voice and typed messages are one continuous
conversation, not two separate histories that happen to share a page.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.services.voice_conversation_service import handle_voice_turn
from app.services.voice_service import read_audio_from_cache, get_tts_provider, save_audio_to_cache
from app.services import conversation_service

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/converse")
async def converse(
    audio: UploadFile = File(...),
    client_id: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    try:
        result = handle_voice_turn(
            db,
            org_id=str(user.org_id),
            user_id=str(user.id),
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            client_id=client_id,
        )
    except RuntimeError as e:
        # Raised by voice_service when STT/TTS isn't configured yet
        raise HTTPException(status_code=503, detail=str(e))

    conv = conversation_service.get_or_create_active_conversation(db, str(user.org_id), str(user.id), context="chat")
    conversation_service.add_message(db, str(conv.id), "user", result["transcript"])
    conversation_service.add_message(db, str(conv.id), "assistant", result["reply_text"])

    return {**result, "conversation_id": str(conv.id)}


@router.get("/audio/{audio_id}")
def get_audio(audio_id: str):
    audio_bytes = read_audio_from_cache(audio_id)
    if not audio_bytes:
        raise HTTPException(status_code=404, detail="Audio not found or expired")
    return Response(content=audio_bytes, media_type="audio/mpeg")


@router.post("/synthesize")
def synthesize(text: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Utility endpoint: turn arbitrary text into speech without a full conversation turn."""
    try:
        audio_bytes = get_tts_provider(db, str(user.org_id)).synthesize(text)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    audio_id = save_audio_to_cache(audio_bytes)
    return {"audio_id": audio_id}
