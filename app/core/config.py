"""
Central application settings, loaded from environment variables / .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://realtyai:realtyai@localhost:5432/realtyai"

    # --- Supabase ---
    # DATABASE_URL above should point at your Supabase Postgres connection
    # string (Project Settings -> Database -> Connection string, use the
    # "Session pooler" or "Transaction pooler" URI for serverless-friendly
    # connections). These three are separate — used for auth verification
    # and Storage, not for the DB connection itself.
    SUPABASE_URL: str = ""               # e.g. https://xxxxx.supabase.co
    SUPABASE_ANON_KEY: str = ""          # public, safe for frontend
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # SECRET — backend only, bypasses RLS, never expose to frontend
    SUPABASE_JWT_SECRET: str = ""        # legacy HS256 fallback; leave blank to use JWKS verification (recommended)
    VOICE_STORAGE_BACKEND: str = "local"  # "local" | "supabase"
    SUPABASE_VOICE_BUCKET: str = "voice-audio"

    # DeepSeek LLM
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # --- Hermes Agent (Nous Research) — delegated deep-work tasks ---
    # Hermes runs as its OWN service (not pip-installable into this app —
    # it has no published wheel; install via their official installer or
    # git clone + uv sync, see mcp_server-style setup notes in
    # app/services/hermes_agent_service.py). This backend talks to it over
    # HTTP via its OpenAI-compatible "API Server" mode:
    #   hermes config set API_SERVER_ENABLED true
    #   hermes config set API_SERVER_KEY <same value as HERMES_API_KEY below>
    # Each request to Hermes spins up a full tool-using agent server-side —
    # it is NOT a fast LLM proxy, so it's used here only for explicitly
    # delegated deep-research/multi-step tasks, never for chat/voice replies.
    HERMES_ENABLED: bool = False
    HERMES_MODEL: str = "deepseek-v4-flash"
    HERMES_API_BASE_URL: str = ""  # e.g. http://your-hermes-host:PORT/v1 — no default guessed, must be set explicitly
    HERMES_API_KEY: str = ""       # must match Hermes' own API_SERVER_KEY config
    HERMES_TIMEOUT_SECONDS: int = 300

    # --- Google OAuth (Gmail + Google Calendar) ---
    # Create credentials at console.cloud.google.com — enable Gmail API and
    # Calendar API, create an OAuth 2.0 Client ID (Web application type).
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/integrations/google/callback"

    # --- Microsoft OAuth (Outlook Mail + Calendar via Graph API) ---
    # Register an app at entra.microsoft.com (Entra ID / Azure AD app
    # registration) — needs Mail.ReadWrite, Mail.Send, Calendars.ReadWrite
    # delegated permissions, admin consent depending on your tenant setup.
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"  # "common" for multi-tenant + personal accounts
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/integrations/microsoft/callback"

    # --- Slack ---
    # Create an app at api.slack.com/apps — needs bot token scopes
    # chat:write, app_mentions:read, im:history, im:write, and Event
    # Subscriptions enabled pointing at /integrations/slack/events.
    SLACK_SIGNING_SECRET: str = ""  # used to verify inbound Slack requests are really from Slack

    # --- Web search (for the Search tab's web results) ---
    # Bing's Search API was retired August 2025 — not an option. Three
    # pluggable options here, see web_search_service.py:
    #   "searxng" — FREE, self-hosted, no API key (recommended default —
    #               run `docker run -d -p 8888:8080 searxng/searxng` and
    #               enable json in its settings.yml's search.formats)
    #   "brave"   — independent index, cheap (~$0.005/query), no tracking
    #   "tavily"  — AI-native, citation-grounded, pricier
    WEB_SEARCH_PROVIDER: str = "searxng"  # "searxng" | "brave" | "tavily" | "none"
    SEARXNG_BASE_URL: str = "http://localhost:8888"
    BRAVE_SEARCH_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # App
    SECRET_KEY: str = "dev-secret-change-me"
    ENVIRONMENT: str = "development"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Vector store
    VECTOR_INDEX_PATH: str = "./data/vector_index"
    VECTOR_META_PATH: str = "./data/vector_meta.json"

    # Trust ladder
    TRUST_THRESHOLD_AUTONOMOUS: int = 75
    TRUST_THRESHOLD_LIMITED: int = 40

    # Listings data source
    LISTINGS_SOURCE: str = "demo"  # default source when not explicitly chosen at ingest time — "demo" | "reso" | "bridge" | "attom"
    RESO_API_BASE_URL: str = ""
    RESO_API_TOKEN: str = ""

    # Bridge Interactive — Zillow Group's OFFICIAL RESO-standard data
    # program (bridgeinteractive.com/developers). This is the legitimate
    # path to Zillow-adjacent data, not a scraper or third-party wrapper.
    BRIDGE_API_BASE_URL: str = ""
    BRIDGE_API_TOKEN: str = ""

    # ATTOM Data — licensed nationwide property/public-records provider (developer.attomdata.com)
    ATTOM_API_KEY: str = ""

    # --- Voice (STT/TTS) ---
    STT_PROVIDER: str = "openai"       # "openai" | "none"
    TTS_PROVIDER: str = "openai"       # "openai" | "elevenlabs" | "none"
    OPENAI_API_KEY: str = ""
    OPENAI_TTS_VOICE: str = "alloy"    # alloy | echo | fable | onyx | nova | shimmer
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""      # e.g. a warm, natural voice ID from your ElevenLabs voice library
    VOICE_CACHE_DIR: str = "./data/voice_cache"

    # --- Telephony (Twilio) — lets clients call a real phone number and talk to Athena ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"  # must be publicly reachable for Twilio webhooks in production

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
