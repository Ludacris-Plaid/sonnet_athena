"""
Encrypts/decrypts third-party CRM credentials (API keys, tokens) at rest.

IMPORTANT: this is app-level encryption (Fernet, symmetric, key derived from
SECRET_KEY) as a floor, not a ceiling. These are live credentials to a
realtor's actual CRM — for a production deployment handling real customer
data, use a real secrets manager (Supabase Vault, AWS Secrets Manager,
HashiCorp Vault) instead of relying on this alone. This module exists so
credentials are never stored as plaintext in the database, not as a claim
that the security story is complete.
"""
import base64
import hashlib
import json

from cryptography.fernet import Fernet

from app.core.config import settings


def _get_fernet() -> Fernet:
    # Derive a valid 32-byte urlsafe-base64 Fernet key from SECRET_KEY so no
    # separate key needs to be generated/managed for this specific purpose.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_credentials(credentials: dict) -> str:
    payload = json.dumps(credentials).encode()
    return _get_fernet().encrypt(payload).decode()


def decrypt_credentials(encrypted: str) -> dict:
    payload = _get_fernet().decrypt(encrypted.encode())
    return json.loads(payload.decode())
