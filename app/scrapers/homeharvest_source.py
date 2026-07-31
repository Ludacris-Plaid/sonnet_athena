"""HomeHarvest-powered scraper for Realtor.com (Redfin/Zillow data source).
723 GitHub stars — well-maintained, handles Cloudflare/bypass, returns MLS-style data
with photos, agent info, and all standard listing fields."""
from app.scrapers.base import ListingsSource
from app.scrapers.search_config import PropertySearchConfig


class HomeHarvestSource(ListingsSource):
    """Uses the HomeHarvest library to scrape property data from Realtor.com.
    Supports all search filters and returns normalized listing dicts compatible
    with the Property model. Handles anti-bot protection internally."""

    def __init__(self, config: PropertySearchConfig | None = None):
        self.config = config or PropertySearchConfig()

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        cfg = PropertySearchConfig(city=city, state=state, max_results=limit)
        return self.search(cfg)

    def search(self, config: PropertySearchConfig) -> list[dict]:
        from homeharvest import scrape_property

        location = f"{config.city}, {config.state}" if config.city and config.state else config.city or ""
        if not location:
            return []

        try:
            df = scrape_property(
                location=location,
                listing_type="for_sale",
                property_type=self._map_property_type(config.property_type),
                beds_min=config.beds_min,
                beds_max=config.beds_max,
                baths_min=config.baths_min,
                baths_max=config.baths_max,
                sqft_min=config.sqft_min,
                sqft_max=config.sqft_max,
                price_min=config.price_min,
                price_max=config.price_max,
                limit=config.max_results,
            )
        except Exception:
            return []

        if df is None or df.empty:
            return []

        listings = []
        for _, row in df.iterrows():
            try:
                # Extract primary photo from photos column
                photos = self._extract_photos(row)
                address = self._get_address(row)

                listing = {
                    "address": address,
                    "city": row.get("city", config.city or ""),
                    "state": row.get("state", config.state or ""),
                    "postal_code": row.get("zip_code", ""),
                    "price": row.get("list_price"),
                    "beds": row.get("beds"),
                    "baths": None,
                    "sqft": int(row["sqft"]) if row.get("sqft") else None,
                    "property_type": (row.get("style") or "").lower().replace(" ", "_") or config.property_type or "single_family",
                    "status": row.get("status", "active"),
                    "mls_number": row.get("mls_id", ""),
                    "listing_agent_name": row.get("agent_name", ""),
                    "listing_agent_email": row.get("agent_email", ""),
                    "listing_agent_phone": row.get("agent_phone", ""),
                    "listing_brokerage": row.get("broker_name", ""),
                    "source": "realtor_com",
                    "source_listing_id": row.get("listing_id") or row.get("property_id", ""),
                    "source_url": row.get("property_url", row.get("permalink", "")),
                    "description": row.get("text", ""),
                    "thumbnail_url": photos[0] if photos else "",
                    "photos": photos,
                    "year_built": int(row["year_built"]) if row.get("year_built") else None,
                    "garage_spaces": int(row["garage"]) if row.get("garage") else None,
                    "lot_size_sqft": int(row["lot_sqft"]) if row.get("lot_sqft") else None,
                    "lot_size_sqft": int(row["lot_sqft"]) if row.get("lot_sqft") else None,
                    "garage_spaces": int(row["garage"]) if row.get("garage") else None,
                }
                listings.append(listing)
            except Exception:
                continue

        return listings[:config.max_results]

    def _get_address(self, row) -> str:
        parts = []
        for key in ["street", "unit", "city", "state", "zip_code"]:
            val = row.get(key)
            if val is not None:
                try:
                    if not pd.isna(val):
                        parts.append(str(val))
                except Exception:
                    parts.append(str(val))
        return " ".join(parts).strip() or "Unknown"

    def _extract_photos(self, row) -> list[str]:
        photos = row.get("photos", [])
        if isinstance(photos, list):
            return photos
        try:
            if pd.isna(photos):
                return []
        except Exception:
            pass
        return [photos]

    def _map_property_type(self, pt: str | None) -> list[str] | None:
        if not pt:
            return None
        mapping = {
            "single_family": ["single_family"],
            "condo": ["condos", "condo_townhome"],
            "townhouse": ["townhomes", "condo_townhome"],
            "multi_family": ["multi_family"],
            "land": ["land"],
        }
        return mapping.get(pt, None)


import pandas as pd
