"""
ATTOM Data connector — a licensed, paid nationwide property/public-records
data provider (api.gateway.attomdata.com), a real alternative to MLS/RESO
access for agents who don't have MLS-affiliated Bridge access or want
broader public-records coverage (tax history, prior sales, etc.) alongside
listings. Requires an ATTOM API key (developer.attomdata.com).
"""
import httpx

from app.core.config import settings
from app.scrapers.base import ListingsSource

BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"


class AttomDataSource(ListingsSource):
    def __init__(self):
        if not settings.ATTOM_API_KEY:
            raise RuntimeError("ATTOM_API_KEY not configured. Get one at developer.attomdata.com.")
        self.api_key = settings.ATTOM_API_KEY

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        headers = {"apikey": self.api_key, "Accept": "application/json"}
        params = {"address2": f"{city}, {state}", "pagesize": limit}

        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{BASE_URL}/property/snapshot", headers=headers, params=params)
            resp.raise_for_status()
            properties = resp.json().get("property", [])
        return [self._normalize(p) for p in properties]

    def _normalize(self, p: dict) -> dict:
        address = p.get("address", {})
        building = p.get("building", {})
        lot = p.get("lot", {})
        summary = p.get("summary", {})
        sale = p.get("sale", {})

        return {
            "address": address.get("line1"),
            "city": address.get("locality"),
            "state": address.get("countrySubd"),
            "postal_code": address.get("postal1"),
            "latitude": p.get("location", {}).get("latitude"),
            "longitude": p.get("location", {}).get("longitude"),
            "price": sale.get("amount", {}).get("saleAmt"),
            "beds": building.get("rooms", {}).get("beds"),
            "baths": building.get("rooms", {}).get("bathsTotal"),
            "sqft": building.get("size", {}).get("universalSize"),
            "property_type": summary.get("propType"),
            "year_built": summary.get("yearBuilt"),
            "status": "active",  # ATTOM's snapshot endpoint is public-records data, not live MLS status
            "days_on_market": None,
            "description": None,  # ATTOM doesn't provide marketing remarks — it's a public-records source, not a listing feed
            "thumbnail_url": None,
            "photos": None,
            "mls_number": None,
            "lot_size_sqft": lot.get("lotSize2"),
            "garage_spaces": None,
            "listing_agent_name": None,  # ATTOM is public-records data — no listing agent info; use Bridge/RESO for that
            "listing_agent_email": None,
            "listing_agent_phone": None,
            "listing_brokerage": None,
            "source": "attom",
            "source_listing_id": p.get("identifier", {}).get("attomId"),
            "source_url": None,
            "raw_data": p,
        }
