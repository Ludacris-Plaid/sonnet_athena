"""
Client for a Hermes Agent instance (Nous Research, nousresearch.com/hermes-agent),
running in its own process/server with API Server mode enabled.

Architecture note, worth reading before wiring more calls through this:
Hermes' API server is "an agent runtime, not a pure LLM proxy" (per their own
docs) — every request spins up a server-side AIAgent with its full toolset
(terminal, file, web search, memory, skills) and can take a genuinely long
time (the timeout below defaults to 5 minutes, not seconds). That's the
right tool for a delegated research/analysis task an agent explicitly asks
Athena to "go deep" on — a multi-property investment comparison, a
neighborhood deep-dive across several data sources, drafting a full
transaction plan. It is the WRONG tool for chat replies, voice turns, or
anything else on the fast path — use llm_service (DeepSeek) for those, same
as everywhere else in this codebase.

Setup (Hermes runs as a separate service, not part of this repo):
  1. Install Hermes on its own host: curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  2. Configure a model provider for Hermes itself: `hermes model`
  3. Enable the API server:
       hermes config set API_SERVER_ENABLED true
       hermes config set API_SERVER_KEY <a-secret-you-choose>
  4. Start it (see Hermes' own docs for the current server-start command —
     confirm against `hermes --help` / their docs for your installed
     version, since this is a fast-moving young project).
  5. Set HERMES_ENABLED=true, HERMES_API_BASE_URL, and HERMES_API_KEY
     (matching step 3's API_SERVER_KEY) in this app's .env.
"""
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class HermesResponse:
    text: str
    raw: dict


class HermesNotConfiguredError(RuntimeError):
    pass


def is_hermes_available() -> bool:
    return settings.HERMES_ENABLED and bool(settings.HERMES_API_BASE_URL) and bool(settings.HERMES_API_KEY)


def delegate_task(prompt: str, system_context: str | None = None) -> HermesResponse:
    """
    Hands a task to Hermes and waits for the full result. Given Hermes runs
    real tools server-side per the architecture note above, this is a
    synchronous, potentially slow call by design — callers (routes_agent.py)
    should treat it like a background job from the frontend's perspective
    (show a "working on it" state), not a snappy chat response.
    """
    if not is_hermes_available():
        raise HermesNotConfiguredError(
            "Hermes Agent isn't configured. Set HERMES_ENABLED=true, HERMES_API_BASE_URL, "
            "and HERMES_API_KEY in .env — see app/services/hermes_agent_service.py for setup steps."
        )

    messages = []
    if system_context:
        messages.append({"role": "system", "content": system_context})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {settings.HERMES_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.HERMES_MODEL,  # model to use for Go Deep delegation
        "messages": messages,      # for via `hermes model` — this field is effectively a label, not a routing choice.
    }

    base_url = settings.HERMES_API_BASE_URL.rstrip("/")
    with httpx.Client(timeout=settings.HERMES_TIMEOUT_SECONDS) as client:
        resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return HermesResponse(text=text, raw=data)
