"""
Bridge Interactive connector — Zillow Group's OFFICIAL, RESO-standard data
program. This is the legitimate path to Zillow-adjacent data (public
records, Zestimates where licensed) and broad MLS coverage — NOT a
scraper, NOT a third-party wrapper around scraping. Requires approval as
an MLS-affiliated brokerage or approved technology partner
(bridgeinteractive.com/developers) — approval can take weeks and isn't
guaranteed for independent developers.

Because Bridge is itself RESO Web API-standard, this connector is
structurally almost identical to reso_client.py — same query pattern,
same auth style (bearer token), different base URL and (potentially)
different field availability depending on what your specific Bridge
dataset access includes (e.g. Zestimate/public-records fields are a
separate licensed dataset within Bridge, not automatically included).

Do NOT point this at any unofficial "Zillow API" (RapidAPI listings,
Apify actors, Zillapi-style wrappers, etc.) — those are unofficial
scraping wrappers, not Bridge, and using one exposes every customer of
this platform to the same ToS/legal risk direct scraping would, with the
added problem that the wrapper service itself can disappear or get cut
off by Zillow at any time, silently breaking this integration for
everyone relying on it.
"""
import httpx

from app.core.config import settings
from app.scrapers.base import ListingsSource


class BridgeInteractiveSource(ListingsSource):
    def __init__(self):
        if not settings.BRIDGE_API_BASE_URL or not settings.BRIDGE_API_TOKEN:
            raise RuntimeError(
                "BRIDGE_API_BASE_URL / BRIDGE_API_TOKEN not configured. "
                "Apply for Bridge Interactive access at bridgeinteractive.com/developers "
                "— requires MLS affiliation or approved-partner status."
            )
        self.base_url = settings.BRIDGE_API_BASE_URL.rstrip("/")
        self.token = settings.BRIDGE_API_TOKEN

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {
            "access_token": self.token,
            "$filter": f"City eq '{city}' and StateOrProvince eq '{state}'",
            "$top": limit,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.base_url}/Property", headers=headers, params=params)
            resp.raise_for_status()
            raw = resp.json().get("value", [])
        return [self._normalize(item) for item in raw]

    def _normalize(self, item: dict) -> dict:
        # Bridge uses the same RESO Data Dictionary field names as any
        # certified MLS feed — adjust only if your specific Bridge dataset
        # deviates. Photos/media come through the RESO Media resource
        # separately in a real Bridge integration (a second API call per
        # listing, `/Media?$filter=ResourceRecordKey eq '{listing_id}'`) —
        # stubbed as empty here since that's a genuinely separate request
        # this method doesn't make; wire it in if/when Bridge access is live.
        return {
            "address": item.get("UnparsedAddress"),
            "city": item.get("City"),
            "state": item.get("StateOrProvince"),
            "postal_code": item.get("PostalCode"),
            "latitude": item.get("Latitude"),
            "longitude": item.get("Longitude"),
            "price": item.get("ListPrice"),
            "beds": item.get("BedroomsTotal"),
            "baths": item.get("BathroomsTotalInteger"),
            "sqft": item.get("LivingArea"),
            "property_type": item.get("PropertyType"),
            "year_built": item.get("YearBuilt"),
            "status": item.get("StandardStatus", "active").lower(),
            "days_on_market": item.get("DaysOnMarket"),
            "description": item.get("PublicRemarks"),
            "thumbnail_url": None,   # see Media resource note above
            "photos": None,
            "mls_number": item.get("ListingId"),
            "lot_size_sqft": item.get("LotSizeSquareFeet"),
            "garage_spaces": item.get("GarageSpaces"),
            "listing_agent_name": item.get("ListAgentFullName"),
            "listing_agent_email": item.get("ListAgentEmail"),
            "listing_agent_phone": item.get("ListAgentPreferredPhone"),
            "listing_brokerage": item.get("ListOfficeName"),
            "source": "bridge",
            "source_listing_id": item.get("ListingId"),
            "source_url": None,
            "raw_data": item,
        }
