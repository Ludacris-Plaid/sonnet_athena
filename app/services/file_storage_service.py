"""
Generic file storage, pluggable between local disk and Supabase Storage —
same pattern as voice_service.py's audio cache, generalized for arbitrary
files (uploaded documents). Kept as a separate module rather than sharing
code with voice_service.py to avoid touching that already-verified path;
a future cleanup could unify them behind one interface.
"""
import uuid
from pathlib import Path

from app.core.config import settings

DOCUMENT_STORAGE_DIR = "./data/documents"
DOCUMENT_BUCKET = "documents"


def _local_save(file_bytes: bytes, extension: str) -> str:
    storage_dir = Path(DOCUMENT_STORAGE_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    with open(storage_dir / f"{file_id}.{extension}", "wb") as f:
        f.write(file_bytes)
    return file_id


def _local_read(file_id: str, extension: str) -> bytes | None:
    path = Path(DOCUMENT_STORAGE_DIR) / f"{file_id}.{extension}"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return f.read()


def _supabase_client():
    from supabase import create_client

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY required for Supabase file storage")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _supabase_save(file_bytes: bytes, extension: str) -> str:
    file_id = str(uuid.uuid4())
    client = _supabase_client()
    client.storage.from_(DOCUMENT_BUCKET).upload(f"{file_id}.{extension}", file_bytes)
    return file_id


def _supabase_read(file_id: str, extension: str) -> bytes | None:
    client = _supabase_client()
    try:
        return client.storage.from_(DOCUMENT_BUCKET).download(f"{file_id}.{extension}")
    except Exception:
        return None


def save_file(file_bytes: bytes, extension: str) -> str:
    if settings.VOICE_STORAGE_BACKEND == "supabase":  # same backend switch as voice; one knob for "use Supabase Storage"
        return _supabase_save(file_bytes, extension)
    return _local_save(file_bytes, extension)


def read_file(file_id: str, extension: str) -> bytes | None:
    if settings.VOICE_STORAGE_BACKEND == "supabase":
        return _supabase_read(file_id, extension)
    return _local_read(file_id, extension)
