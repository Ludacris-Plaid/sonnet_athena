"""
Runtime-configurable settings — the actual mechanism behind "add an API
key in Settings and have it work immediately," rather than requiring a
.env edit and a server restart.

KEY_REGISTRY is the single source of truth for every configurable key in
the platform: which scope it belongs to (org-level, user-editable in
regular Settings; or platform-level, admin-only), what category it's
grouped under in the UI, a human label/help text, and whether it's a
secret (masked in the UI) or a plain choice (like a provider name).
"""
from app.core.config import settings as env_settings
from app.models.platform_setting import PlatformSetting
from app.services.crm_credential_service import encrypt_credentials, decrypt_credentials

# scope: "org" (editable in regular Settings) | "platform" (admin-only)
KEY_REGISTRY = {
    "STT_PROVIDER": {"scope": "org", "category": "Voice", "label": "Speech-to-text provider", "secret": False, "choices": ["openai", "none"]},
    "TTS_PROVIDER": {"scope": "org", "category": "Voice", "label": "Text-to-speech provider", "secret": False, "choices": ["openai", "elevenlabs", "none"]},
    "OPENAI_API_KEY": {"scope": "org", "category": "Voice", "label": "OpenAI API key (for voice)", "secret": True},
    "OPENAI_TTS_VOICE": {"scope": "org", "category": "Voice", "label": "OpenAI voice", "secret": False, "choices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]},
    "ELEVENLABS_API_KEY": {"scope": "org", "category": "Voice", "label": "ElevenLabs API key", "secret": True},
    "ELEVENLABS_VOICE_ID": {"scope": "org", "category": "Voice", "label": "ElevenLabs voice ID", "secret": False},

    "RESO_API_BASE_URL": {"scope": "org", "category": "Listings Data", "label": "MLS/RESO API base URL", "secret": False},
    "RESO_API_TOKEN": {"scope": "org", "category": "Listings Data", "label": "MLS/RESO API token", "secret": True},
    "BRIDGE_API_BASE_URL": {"scope": "org", "category": "Listings Data", "label": "Bridge Interactive base URL", "secret": False},
    "BRIDGE_API_TOKEN": {"scope": "org", "category": "Listings Data", "label": "Bridge Interactive token", "secret": True},
    "ATTOM_API_KEY": {"scope": "org", "category": "Listings Data", "label": "ATTOM Data API key", "secret": True},

    "WEB_SEARCH_PROVIDER": {"scope": "org", "category": "Web Search", "label": "Web search provider", "secret": False, "choices": ["searxng", "brave", "tavily", "none"]},
    "SEARXNG_BASE_URL": {"scope": "org", "category": "Web Search", "label": "SearXNG instance URL (free, self-hosted)", "secret": False},
    "BRAVE_SEARCH_API_KEY": {"scope": "org", "category": "Web Search", "label": "Brave Search API key", "secret": True},
    "TAVILY_API_KEY": {"scope": "org", "category": "Web Search", "label": "Tavily API key", "secret": True},

    "SLACK_SIGNING_SECRET": {"scope": "org", "category": "Slack", "label": "Slack signing secret", "secret": True},

    "DEEPSEEK_API_KEY": {"scope": "platform", "category": "Core AI", "label": "DeepSeek API key", "secret": True},
    "SUPABASE_URL": {"scope": "platform", "category": "Infrastructure", "label": "Supabase URL", "secret": False},
    "SUPABASE_SERVICE_ROLE_KEY": {"scope": "platform", "category": "Infrastructure", "label": "Supabase service role key", "secret": True},
    "GOOGLE_CLIENT_ID": {"scope": "platform", "category": "OAuth Apps", "label": "Google OAuth client ID", "secret": False},
    "GOOGLE_CLIENT_SECRET": {"scope": "platform", "category": "OAuth Apps", "label": "Google OAuth client secret", "secret": True},
    "MICROSOFT_CLIENT_ID": {"scope": "platform", "category": "OAuth Apps", "label": "Microsoft OAuth client ID", "secret": False},
    "MICROSOFT_CLIENT_SECRET": {"scope": "platform", "category": "OAuth Apps", "label": "Microsoft OAuth client secret", "secret": True},
    "TWILIO_ACCOUNT_SID": {"scope": "platform", "category": "Telephony", "label": "Twilio account SID", "secret": False},
    "TWILIO_AUTH_TOKEN": {"scope": "platform", "category": "Telephony", "label": "Twilio auth token", "secret": True},
    "TWILIO_PHONE_NUMBER": {"scope": "platform", "category": "Telephony", "label": "Twilio phone number", "secret": False},
    "HERMES_API_BASE_URL": {"scope": "platform", "category": "Deep Research (Hermes)", "label": "Hermes API base URL", "secret": False},
    "HERMES_API_KEY": {"scope": "platform", "category": "Deep Research (Hermes)", "label": "Hermes API key", "secret": True},
}


def get_effective_setting(db, org_id: str | None, key: str) -> str | None:
    """DB override first (org-scoped, then platform-scoped), falls back to the .env-loaded default."""
    if key not in KEY_REGISTRY:
        raise ValueError(f"Unknown setting key: {key}")

    if org_id and KEY_REGISTRY[key]["scope"] == "org":
        row = db.query(PlatformSetting).filter(PlatformSetting.org_id == org_id, PlatformSetting.key == key).first()
        if row:
            return decrypt_credentials(row.encrypted_value)["value"]

    row = db.query(PlatformSetting).filter(PlatformSetting.org_id.is_(None), PlatformSetting.key == key).first()
    if row:
        return decrypt_credentials(row.encrypted_value)["value"]

    return getattr(env_settings, key, None)


def set_setting(db, org_id: str | None, key: str, value: str) -> None:
    if key not in KEY_REGISTRY:
        raise ValueError(f"Unknown setting key: {key}")
    expected_scope = KEY_REGISTRY[key]["scope"]
    if expected_scope == "platform" and org_id is not None:
        raise ValueError(f"{key} is a platform-wide setting — must be set from the Admin dashboard, not per-org Settings.")

    encrypted = encrypt_credentials({"value": value})
    existing = db.query(PlatformSetting).filter(PlatformSetting.org_id == org_id, PlatformSetting.key == key).first()
    if existing:
        existing.encrypted_value = encrypted
        db.add(existing)
    else:
        db.add(PlatformSetting(org_id=org_id, key=key, encrypted_value=encrypted))
    db.commit()


def delete_setting(db, org_id: str | None, key: str) -> None:
    db.query(PlatformSetting).filter(PlatformSetting.org_id == org_id, PlatformSetting.key == key).delete()
    db.commit()


def list_settings_for_scope(db, org_id: str | None, scope: str) -> list[dict]:
    """Returns every key in that scope with masked values and whether it's configured (DB override or .env default)."""
    results = []
    for key, meta in KEY_REGISTRY.items():
        if meta["scope"] != scope:
            continue
        target_org = org_id if scope == "org" else None
        row = db.query(PlatformSetting).filter(PlatformSetting.org_id == target_org, PlatformSetting.key == key).first()
        env_default = getattr(env_settings, key, None)
        db_value = decrypt_credentials(row.encrypted_value)["value"] if row else None
        display_value = _mask(db_value) if (row and meta["secret"]) else (db_value if row else (env_default if not meta["secret"] else None))
        results.append({
            "key": key, **meta,
            "is_set_in_db": row is not None,
            "is_set_in_env": bool(env_default),
            "display_value": display_value,
        })
    return results


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return value[:4] + "•" * (len(value) - 8) + value[-4:]
