"""Flexible search configuration for real estate listing scrapers.
Serializable to JSON for Athena tool arguments, supports all major
search dimensions used by Zillow/Redfin public search pages."""

from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class PropertySearchConfig:
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    beds_min: Optional[int] = None
    beds_max: Optional[int] = None
    baths_min: Optional[int] = None
    baths_max: Optional[int] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    sqft_min: Optional[int] = None
    sqft_max: Optional[int] = None
    property_type: Optional[str] = None   # house, condo, townhouse, multi_family, land
    listing_status: str = "for_sale"       # for_sale, for_rent, sold
    sort: str = "newest"                   # newest, price_low, price_high, sqft
    max_pages: int = 3                     # how many result pages to scrape
    use_stealth: bool = True
    use_proxy: bool = True
    max_results: int = 50

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_search_query(self) -> str:
        """Build a human-readable description from config."""
        parts = []
        if self.city:
            parts.append(f"in {self.city}")
        if self.state:
            parts.append(self.state)
        price = []
        if self.price_min:
            price.append(f"${self.price_min:,}")
        if self.price_max:
            price.append(f"${self.price_max:,}")
        if price:
            parts.append(" to ".join(price))
        if self.beds_min:
            parts.append(f"{self.beds_min}+ beds")
        if self.baths_min:
            parts.append(f"{self.baths_min}+ baths")
        return " ".join(parts) or "any property"

    @classmethod
    def from_command(cls, args: dict) -> "PropertySearchConfig":
        """Build from Athena tool arguments dict."""
        return cls(
            city=args.get("city"),
            state=args.get("state") or args.get("province"),
            postal_code=args.get("postal_code") or args.get("zip"),
            beds_min=args.get("beds_min") or args.get("min_beds"),
            baths_min=args.get("baths_min") or args.get("min_baths"),
            price_min=args.get("price_min") or args.get("min_price"),
            price_max=args.get("price_max") or args.get("max_price"),
            sqft_min=args.get("sqft_min"),
            property_type=args.get("property_type") or args.get("home_type"),
            listing_status=args.get("listing_status") or args.get("status", "for_sale"),
            max_pages=min(args.get("max_pages", 3), 5),
            max_results=min(args.get("max_results", 50), 200),
        )
