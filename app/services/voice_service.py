"""
Speech-to-text and text-to-speech, abstracted behind provider interfaces so
the platform isn't locked to one vendor. Real HTTP integrations, not mocked.

STT: OpenAI's Whisper API (audio/transcriptions).
TTS: OpenAI's TTS API by default, or ElevenLabs if configured — ElevenLabs
     generally sounds more natural/less robotic, which matters a lot for a
     product explicitly going for a "warm, friend-like" voice.

DeepSeek (the primary LLM) doesn't offer voice endpoints, hence the separate
provider here — this is the one place in the platform that intentionally
uses a different vendor, clearly contained to this module.
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.core.config import settings


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------

class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        raise NotImplementedError


class OpenAIWhisperSTT(STTProvider):
    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set — required for STT_PROVIDER=openai")
        self.api_key = api_key

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": (filename, audio_bytes)}
        data = {"model": "whisper-1"}
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
            )
            resp.raise_for_status()
            return resp.json()["text"]


class NoOpSTT(STTProvider):
    """Used when STT_PROVIDER=none — lets the rest of the pipeline be tested
    without a live API key by requiring the caller to pass text directly."""

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        raise RuntimeError("STT is not configured. Set it up under Settings > Voice, or STT_PROVIDER/OPENAI_API_KEY in .env")



class LocalWhisperSTT(STTProvider):
    """Local faster-whisper transcription — no API key needed."""

    _model = None

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size

    def _get_model(self):
        if LocalWhisperSTT._model is None:
            from faster_whisper import WhisperModel
            LocalWhisperSTT._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return LocalWhisperSTT._model

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        import tempfile
        model = self._get_model()
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, _ = model.transcribe(tmp.name)
            return "".join(seg.text for seg in segments).strip()

def get_stt_provider(db=None, org_id: str | None = None) -> STTProvider:
    """
    db/org_id optional so existing callers that don't have a request-scoped
    session (rare) still work off pure .env defaults — but every real call
    site should pass both so a user's own Settings > Voice configuration
    (e.g. their own OpenAI key) actually takes effect.
    """
    provider, api_key = _resolve_stt_config(db, org_id)
    if provider == "openai":
        return OpenAIWhisperSTT(api_key)
    if provider == "local":
        return LocalWhisperSTT()
    return NoOpSTT()


def _resolve_stt_config(db, org_id: str | None) -> tuple[str, str]:
    if db is not None and org_id is not None:
        from app.services.settings_service import get_effective_setting
        return get_effective_setting(db, org_id, "STT_PROVIDER"), get_effective_setting(db, org_id, "OPENAI_API_KEY")
    return settings.STT_PROVIDER, settings.OPENAI_API_KEY


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Return raw audio bytes (mp3)."""
        raise NotImplementedError


class OpenAITTS(TTSProvider):
    def __init__(self, api_key: str, voice: str):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set — required for TTS_PROVIDER=openai")
        self.api_key = api_key
        self.voice = voice

    def synthesize(self, text: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": "tts-1", "voice": self.voice, "input": text}
        with httpx.Client(timeout=60) as client:
            resp = client.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content


class ElevenLabsTTS(TTSProvider):
    def __init__(self, api_key: str, voice_id: str):
        if not api_key or not voice_id:
            raise RuntimeError(
                "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set — required for TTS_PROVIDER=elevenlabs. "
                "Configure under Settings > Voice, or in .env."
            )
        self.api_key = api_key
        self.voice_id = voice_id

    def synthesize(self, text: str) -> bytes:
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8},
        }
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            return resp.content


class NoOpTTS(TTSProvider):
    def synthesize(self, text: str) -> bytes:
        raise RuntimeError("TTS is not configured. Set it up under Settings > Voice, or TTS_PROVIDER + a matching key in .env")



class EdgeTTS(TTSProvider):
    """Free Microsoft Edge TTS — no API key needed."""

    def __init__(self, voice: str = "en-GB-SoniaNeural"):
        self.voice = voice

    def synthesize(self, text: str) -> bytes:
        import asyncio, edge_tts, tempfile, os

        async def _save(path):
            await edge_tts.Communicate(text, self.voice).save(path)

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        try:
            try:
                asyncio.run(_save(tmp.name))
            except RuntimeError:
                # Already inside an event loop — run in a fresh loop via thread
                import threading
                result = {}
                def _runner():
                    try:
                        asyncio.run(_save(tmp.name))
                        result["ok"] = True
                    except Exception as e:
                        result["err"] = e
                t = threading.Thread(target=_runner)
                t.start()
                t.join()
                if "err" in result:
                    raise result["err"]
            with open(tmp.name, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp.name)

def get_tts_provider(db=None, org_id: str | None = None) -> TTSProvider:
    provider, openai_key, openai_voice, eleven_key, eleven_voice_id = _resolve_tts_config(db, org_id)
    if provider == "elevenlabs":
        return ElevenLabsTTS(eleven_key, eleven_voice_id)
    if provider == "openai":
        return OpenAITTS(openai_key, openai_voice)
    if provider == "edge-tts":
        return EdgeTTS()
    return NoOpTTS()


def _resolve_tts_config(db, org_id: str | None) -> tuple[str, str, str, str, str]:
    if db is not None and org_id is not None:
        from app.services.settings_service import get_effective_setting
        return (
            get_effective_setting(db, org_id, "TTS_PROVIDER"),
            get_effective_setting(db, org_id, "OPENAI_API_KEY"),
            get_effective_setting(db, org_id, "OPENAI_TTS_VOICE"),
            get_effective_setting(db, org_id, "ELEVENLABS_API_KEY"),
            get_effective_setting(db, org_id, "ELEVENLABS_VOICE_ID"),
        )
    return settings.TTS_PROVIDER, settings.OPENAI_API_KEY, settings.OPENAI_TTS_VOICE, settings.ELEVENLABS_API_KEY, settings.ELEVENLABS_VOICE_ID


# ---------------------------------------------------------------------------
# Audio file cache — synthesized replies are written to storage and served
# back by URL, since Twilio's <Play> verb and the browser <audio> tag both
# need a URL rather than raw bytes in the response they trigger from.
#
# Pluggable: "local" writes to disk (fine for a single instance / dev), or
# "supabase" uses Supabase Storage (needed once you run more than one API
# instance, since local disk isn't shared across them).
# ---------------------------------------------------------------------------

def _local_save(audio_bytes: bytes) -> str:
    cache_dir = Path(settings.VOICE_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_id = str(uuid.uuid4())
    with open(cache_dir / f"{audio_id}.mp3", "wb") as f:
        f.write(audio_bytes)
    return audio_id


def _local_read(audio_id: str) -> bytes | None:
    path = Path(settings.VOICE_CACHE_DIR) / f"{audio_id}.mp3"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return f.read()


def _supabase_client():
    from supabase import create_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY required for VOICE_STORAGE_BACKEND=supabase")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _supabase_save(audio_bytes: bytes) -> str:
    audio_id = str(uuid.uuid4())
    client = _supabase_client()
    client.storage.from_(settings.SUPABASE_VOICE_BUCKET).upload(
        f"{audio_id}.mp3", audio_bytes, {"content-type": "audio/mpeg"}
    )
    return audio_id


def _supabase_read(audio_id: str) -> bytes | None:
    client = _supabase_client()
    try:
        return client.storage.from_(settings.SUPABASE_VOICE_BUCKET).download(f"{audio_id}.mp3")
    except Exception:
        return None


def save_audio_to_cache(audio_bytes: bytes) -> str:
    if settings.VOICE_STORAGE_BACKEND == "supabase":
        return _supabase_save(audio_bytes)
    return _local_save(audio_bytes)


def read_audio_from_cache(audio_id: str) -> bytes | None:
    if settings.VOICE_STORAGE_BACKEND == "supabase":
        return _supabase_read(audio_id)
    return _local_read(audio_id)
