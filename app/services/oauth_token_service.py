"""
Shared OAuth2 token refresh logic for Google and Microsoft (both use the
standard refresh_token grant, just different token endpoints) — used by
both the email and calendar connectors for each provider, so a token
refresh fix only needs to happen in one place.

Tokens are stored encrypted (crm_credential_service's Fernet helper, which
despite the module name is fully generic — see that file's docstring).
"""
import time

import httpx

from app.core.config import settings
from app.services.crm_credential_service import encrypt_credentials, decrypt_credentials

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MICROSOFT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def exchange_google_code(code: str) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return _normalize_token_response(resp.json())


def exchange_microsoft_code(code: str) -> dict:
    url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant=settings.MICROSOFT_TENANT_ID)
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, data={
            "code": code,
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return _normalize_token_response(resp.json())


def _normalize_token_response(data: dict) -> dict:
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),  # only present on first authorization, not on refresh
        "expires_at": time.time() + data.get("expires_in", 3600),
    }


def get_valid_access_token(encrypted_tokens: str, provider: str) -> tuple[str, str | None]:
    """
    Returns (access_token, new_encrypted_tokens_or_None). If the token was
    refreshed, new_encrypted_tokens is set — caller must save it back to
    the connection row, or the refreshed token is lost on next call.
    """
    tokens = decrypt_credentials(encrypted_tokens)
    if tokens["expires_at"] > time.time() + 60:  # still valid with a minute of headroom
        return tokens["access_token"], None

    if not tokens.get("refresh_token"):
        raise RuntimeError(f"{provider} token expired and no refresh_token is stored — the user needs to reconnect.")

    if provider == "gmail":
        url = GOOGLE_TOKEN_URL
        data = {
            "refresh_token": tokens["refresh_token"],
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        }
    else:
        url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant=settings.MICROSOFT_TENANT_ID)
        data = {
            "refresh_token": tokens["refresh_token"],
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "grant_type": "refresh_token",
        }

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, data=data)
        resp.raise_for_status()
        new_data = resp.json()

    new_tokens = {
        "access_token": new_data["access_token"],
        "refresh_token": new_data.get("refresh_token", tokens["refresh_token"]),  # Google often omits this on refresh
        "expires_at": time.time() + new_data.get("expires_in", 3600),
    }
    return new_tokens["access_token"], encrypt_credentials(new_tokens)
