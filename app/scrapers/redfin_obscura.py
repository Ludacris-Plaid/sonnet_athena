"""Redfin listings scraper powered by Obscura + free rotating proxies.
Mirrors the ZillowObscuraSource pattern with Redfin-specific URL construction
and listing card parsing."""
import re
import json
import time
import math
from app.scrapers.base import ListingsSource
from app.scrapers.obscura_client import obscura
from app.scrapers.proxy_pool import proxy_pool
from app.scrapers.search_config import PropertySearchConfig

class RedfinObscuraSource(ListingsSource):
    def __init__(self, config: PropertySearchConfig | None = None):
        self.config = config or PropertySearchConfig()

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        cfg = PropertySearchConfig(city=city, state=state, max_results=limit,
            max_pages=math.ceil(limit / 20), use_stealth=True, use_proxy=True)
        return self.search(cfg)

    def search(self, config: PropertySearchConfig) -> list[dict]:
        if not obscura.available and not self._can_fallback():
            raise RuntimeError("Obscura not available")

        all_listings: list[dict] = []
        seen: set[str] = set()

        for page in range(1, config.max_pages + 1):
            if len(all_listings) >= config.max_results:
                break
            url = self._build_search_url(config, page)
            try:
                batch = self._scrape_page(url, config)
                for listing in batch:
                    addr = listing.get("address", "")
                    if addr and addr not in seen:
                        seen.add(addr)
                        all_listings.append(listing)
                        if len(all_listings) >= config.max_results:
                            break
                time.sleep(2 + page * 0.5)
            except Exception:
                continue

        return all_listings[:config.max_results]

    def _build_search_url(self, config: PropertySearchConfig, page: int) -> str:
        """Build Redfin search URL with filters."""
        parts = []
        if config.city:
            parts.append(config.city.replace(" ", "-").lower())
        if config.state:
            parts.append(config.state.lower())
        if config.postal_code:
            parts = [config.postal_code]

        location = "-".join(parts)
        url = f"https://www.redfin.com/{location}"

        # Redfin uses query params for filters
        filters = [f"region_id=", f"page={page}"]
        if config.beds_min:
            filters.append(f"min_beds={config.beds_min}")
        if config.baths_min:
            filters.append(f"min_baths={config.baths_min}")
        if config.price_min:
            filters.append(f"min_price={config.price_min}")
        if config.price_max:
            filters.append(f"max_price={config.price_max}")
        if config.sqft_min:
            filters.append(f"min_sqft={config.sqft_min}")
        if config.property_type:
            filters.append(f"property_type={config.property_type}")
        if config.listing_status == "for_rent":
            filters.append("listing_type=rent")
        elif config.listing_status == "sold":
            filters.append("listing_type=sold")

        if len(filters) > 2:
            return f"{url}/filter/{';'.join(filters[1:])}"
        return url

    def _scrape_page(self, url: str, config: PropertySearchConfig) -> list[dict]:
        proxy = proxy_pool.get_proxy() if config.use_proxy else None
        result = obscura.fetch_html(url, stealth=config.use_stealth, timeout=30)

        if proxy and result.html:
            proxy_pool.mark_success(proxy)
        elif proxy:
            proxy_pool.mark_failed(proxy)

        if not result.html:
            return []

        return self._parse_listings(result.html, config)

    def _parse_listings(self, html: str, config: PropertySearchConfig) -> list[dict]:
        listings: list[dict] = []

        # Redfin stores preloaded state in React root or script tag
        match = re.search(r'__REDFIN_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
        if not match:
            match = re.search(r'"searchResults":\s*(\{.*?"homes":\s*\[.*?\])', html, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1))
                homes = (data.get("homes", []) or
                        data.get("searchResults", {}).get("homes", []) or [])
                for home in homes:
                    try:
                        listings.append(self._normalize_home(home, config))
                    except Exception:
                        continue
            except json.JSONDecodeError:
                pass

        # Fallback: parse listing cards from rendered HTML
        if not listings:
            listings = self._parse_cards_fallback(html, config)

        return listings

    def _parse_cards_fallback(self, html: str, config: PropertySearchConfig) -> list[dict]:
        """Fallback: parse individual listing cards from rendered HTML."""
        cards = re.findall(
            r'<div[^>]*class="[^"]*HomeCardContainer[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )
        listings: list[dict] = []
        for card in cards[:config.max_results]:
            try:
                price_m = re.search(r'\$([\d,]+)', card)
                addr_m = re.search(r'<span[^>]*class="[^"]*address[^"]*"[^>]*>(.*?)</span>', card, re.DOTALL)
                beds_m = re.search(r'(\d+)\s*Bed', card)
                baths_m = re.search(r'(\d+(?:\.\d+)?)\s*Bath', card)
                sqft_m = re.search(r'([\d,]+)\s*(?:sq|Sq)\s*(?:ft|Ft)', card)

                listings.append({
                    "address": addr_m.group(1).strip() if addr_m else "Unknown",
                    "city": config.city or "",
                    "state": config.state or "",
                    "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                    "beds": int(beds_m.group(1)) if beds_m else None,
                    "baths": float(baths_m.group(1)) if baths_m else None,
                    "sqft": int(sqft_m.group(1).replace(",", "")) if sqft_m else None,
                    "property_type": config.property_type or "single_family",
                    "status": "active",
                    "source": "redfin",
                })
            except Exception:
                continue
        return listings

    def _normalize_home(self, home: dict, config: PropertySearchConfig) -> dict:
        return {
            "address": home.get("streetLine", {}).get("value", ""),
            "city": home.get("city", config.city or ""),
            "state": home.get("stateCode", config.state or ""),
            "postal_code": home.get("postalCode", {}).get("value", ""),
            "price": home.get("price", {}).get("value"),
            "beds": home.get("beds"),
            "baths": home.get("baths"),
            "sqft": home.get("sqft", {}).get("value"),
            "property_type": (home.get("propertyType") or "single_family").lower(),
            "source_url": f"https://www.redfin.com{home.get('url', '')}" if home.get("url") else "",
            "photos": [],
            "status": "active",
            "source": "redfin",
        }

    def _can_fallback(self) -> bool:
        import shutil
        return shutil.which("npx") is not None
