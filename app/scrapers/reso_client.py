"""
Stub client for a real RESO Web API / MLS IDX feed.

This is the intended production data source. RESO Web API is the standard
most MLSs expose data through; you'll need an IDX/VOW license from the
relevant MLS board to get RESO_API_BASE_URL / RESO_API_TOKEN.

Docs: https://www.reso.org/reso-web-api/

Fill in field mapping in _normalize() once you have real credentials and
have inspected the actual response schema from your MLS provider.
"""
import httpx

from app.core.config import settings
from app.scrapers.base import ListingsSource


class ResoListingsSource(ListingsSource):
    def __init__(self):
        if not settings.RESO_API_BASE_URL or not settings.RESO_API_TOKEN:
            raise RuntimeError(
                "RESO_API_BASE_URL / RESO_API_TOKEN not configured. "
                "Set LISTINGS_SOURCE=demo until you have a licensed MLS/RESO feed."
            )
        self.base_url = settings.RESO_API_BASE_URL.rstrip("/")
        self.token = settings.RESO_API_TOKEN

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {
            "$filter": f"City eq '{city}' and StateOrProvince eq '{state}'",
            "$top": limit,
        }
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.base_url}/Property", headers=headers, params=params)
            resp.raise_for_status()
            raw = resp.json().get("value", [])
        return [self._normalize(item) for item in raw]

    def _normalize(self, item: dict) -> dict:
        # Adjust these keys to match your specific MLS provider's RESO Data Dictionary field names.
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
            "source": "reso",
            "source_listing_id": item.get("ListingId"),
            "source_url": None,
            "raw_data": item,
        }
