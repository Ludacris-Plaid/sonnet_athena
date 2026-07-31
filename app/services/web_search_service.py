"""
Web search provider abstraction, same adapter pattern as everywhere else
in this codebase (CRM connectors, listings sources, email/calendar
connectors) — one interface, pluggable providers, picked via
WEB_SEARCH_PROVIDER in config (or per-org override in Settings > API Keys).

SearXNG (default, recommended): FREE, self-hosted, no API key, no
per-query cost. An open-source (AGPL) metasearch engine aggregating 70+
sources (Google, Bing, DuckDuckGo, Brave, and more) behind one JSON API —
the standard zero-cost search backend for AI agents as of 2026. Requires
running your own instance: `docker run -d -p 8888:8080 searxng/searxng`,
then enable `json` under `search.formats` in its settings.yml (off by
default on public instances to deter scraping — turn it on for your own
private instance). Point SEARXNG_BASE_URL at it.

Brave (paid alternative): independent index, not a Google/Bing wrapper —
Bing's own Search API was retired in August 2025, so that's not an option
regardless. Cheap (~$0.005/query), stable, no tracking — worth it over
SearXNG if you'd rather not run and maintain your own search instance.

Tavily (paid alternative): AI-native, returns cleaned/extracted content
and can include a synthesized answer with citations rather than raw
snippets — better if you want Athena's web results to read like a
grounded summary instead of a list of links. Note: Tavily was acquired by
Nebius in February 2026 — a live platform-consolidation risk worth knowing
about if you're choosing for the long term, not a reason to avoid it today.
"""
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings


class WebSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Returns [{"title", "url", "snippet"}]"""
        raise NotImplementedError


class BraveSearchProvider(WebSearchProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY not configured.")
        headers = {"Accept": "application/json", "X-Subscription-Token": self.api_key}
        params = {"q": query, "count": max_results}
        with httpx.Client(timeout=15) as client:
            resp = client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("web", {}).get("results", [])
        return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")} for r in results[:max_results]]


class TavilySearchProvider(WebSearchProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY not configured.")
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")} for r in data.get("results", [])[:max_results]]


class SearXNGProvider(WebSearchProvider):
    """
    Free, self-hosted, no API key. SearXNG is an open-source (AGPL)
    metasearch engine that aggregates 70+ sources (Google, Bing,
    DuckDuckGo, Brave, and more) behind one JSON API — the standard
    zero-cost search backend for AI agents in 2026 (LiteLLM has native
    support for it). The only requirement is running a SearXNG instance
    somewhere reachable (a small Docker container — see
    docker.io/searxng/searxng — one command: `docker run -d -p
    8888:8080 searxng/searxng`), with `search.formats: [json]` enabled in
    its settings.yml (not on by default, since public instances disable
    it to deter scraping — your own private instance should turn it on).
    """
    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not self.base_url:
            raise RuntimeError("SEARXNG_BASE_URL not configured — point it at your own SearXNG instance.")
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{self.base_url}/search", params={"q": query, "format": "json"})
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")} for r in results[:max_results]]


def get_web_search_provider(db=None, org_id: str | None = None) -> WebSearchProvider | None:
    if db is not None and org_id is not None:
        from app.services.settings_service import get_effective_setting
        provider = get_effective_setting(db, org_id, "WEB_SEARCH_PROVIDER")
        brave_key = get_effective_setting(db, org_id, "BRAVE_SEARCH_API_KEY")
        tavily_key = get_effective_setting(db, org_id, "TAVILY_API_KEY")
        searxng_url = get_effective_setting(db, org_id, "SEARXNG_BASE_URL")
    else:
        provider, brave_key, tavily_key = settings.WEB_SEARCH_PROVIDER, settings.BRAVE_SEARCH_API_KEY, settings.TAVILY_API_KEY
        searxng_url = settings.SEARXNG_BASE_URL

    if provider == "searxng":
        return SearXNGProvider(searxng_url)
    if provider == "brave":
        return BraveSearchProvider(brave_key)
    if provider == "tavily":
        return TavilySearchProvider(tavily_key)
    return None


def search_web(query: str, max_results: int = 5, db=None, org_id: str | None = None) -> list[dict]:
    provider = get_web_search_provider(db, org_id)
    if not provider:
        return []
    try:
        return provider.search(query, max_results)
    except Exception:  # noqa: BLE001 — web search failing shouldn't break the rest of the Search tab's results
        return []
