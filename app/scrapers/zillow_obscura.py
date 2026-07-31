"""Zillow scraper powered by Obscura stealth browser + proxy rotation.
Extracts: address, city, state, price, beds, baths, sqft, property_type,
MLS number, listing agent, brokerage, photos, source URL, postal code."""
import re
import json
import time
import math
from typing import Optional
from urllib.parse import quote
from app.scrapers.base import ListingsSource
from app.scrapers.obscura_client import obscura
from app.scrapers.proxy_pool import proxy_pool
from app.scrapers.search_config import PropertySearchConfig

PRICE_RE = re.compile(r"(?:C\s*\$\s*|\$\s*)([\d,]+)")
BEDS_RE = re.compile(r"(\d+)\s*bds?\s*$")
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*bas?\s*$")
SQFT_RE = re.compile(r"([\d,]+)\s*(?:sqft|sq\s*ft|sq\.ft\.)", re.IGNORECASE)
MLS_RE = re.compile(r"MLS[®#]?\s*(?:ID\s*)?[#]?\s*([A-Z]\d+)")
IMG_RE = re.compile(r'(?:https?://[^"\s]+\.(?:jpg|jpeg|png|webp)[^"\s]*)', re.IGNORECASE)
AGE_RE = re.compile(r"(\d+)\s*(hours?|days?|weeks?|months?)\s+ago", re.IGNORECASE)


class ZillowObscuraSource(ListingsSource):
    """Scrapes Zillow using Obscura stealth browser. Returns normalized listing dicts
    compatible with the Property model. Supports all search filters via PropertySearchConfig."""

    def __init__(self, config: Optional[PropertySearchConfig] = None):
        self.config = config or PropertySearchConfig()

    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        cfg = PropertySearchConfig(
            city=city, state=state, max_results=limit,
            max_pages=math.ceil(limit / 20), use_stealth=True)
        return self.search(cfg)

    def search(self, config: PropertySearchConfig) -> list[dict]:
        if not obscura.available:
            raise RuntimeError("Obscura not available. Install: npm install -g obscura-node "
                               "or download binary from https://github.com/h4ckf0r0day/obscura/releases")

        all_listings: list[dict] = []
        seen_addresses: set[str] = set()

        for page in range(1, config.max_pages + 1):
            if len(all_listings) >= config.max_results:
                break
            url = self._build_search_url(config, page)
            try:
                batch = self._scrape_page(url, config)
                for listing in batch:
                    addr = listing.get("address", "")
                    if addr and addr not in seen_addresses:
                        seen_addresses.add(addr)
                        all_listings.append(listing)
                        if len(all_listings) >= config.max_results:
                            break
                time.sleep(2 + page * 0.5)  # polite crawl delay
            except Exception as e:
                continue

        return all_listings[:config.max_results]

    def _build_search_url(self, config: PropertySearchConfig, page: int) -> str:
        base = f"https://www.zillow.com/{config.city.replace(' ', '-').lower()}-{config.state.upper()[:2]}" if config.city else "https://www.zillow.com/homes"
        params = []
        if config.beds_min:
            params.append(f'"beds":{{"min":{config.beds_min}}}')
        if config.baths_min:
            params.append(f'"baths":{{"min":{config.baths_min}}}')
        if config.price_min:
            params.append(f'"price":{{"min":{config.price_min}}}')
        if config.price_max:
            params.append(f'"price":{{"max":{config.price_max}}}')
        params.append(f'"pagination":{{"currentPage":{page}}}')
        qs = "{" + ",".join(params) + "}"
        return f"{base}/?searchQueryState={quote(qs, safe='')}"

    def _scrape_page(self, url: str, config: PropertySearchConfig) -> list[dict]:
        # Fetch text for structured data and HTML for images
        result_text = obscura.fetch(url, stealth=True, dump="text", timeout=30, wait=4)
        text = result_text.text if result_text else ""

        listings = self._parse_text_listings(text, config)

        # Fetch HTML to extract images for each listing
        if listings:
            try:
                result_html = obscura.fetch_html(url, stealth=True, timeout=25)
                if result_html:
                    html_content = result_html.html or result_html.text or ""
                    if html_content:
                        thumbs = self._extract_images_from_html(html_content, len(listings))
                        for i, listing in enumerate(listings):
                            if i < len(thumbs):
                                listing["thumbnail_url"] = thumbs[i]
                                listing["photos"] = [thumbs[i]]
            except Exception:
                pass

        return listings

    def _parse_text_listings(self, text: str, config: PropertySearchConfig) -> list[dict]:
        """Parse Zillow text output where each listing block has price, beds, baths, sqft, address, MLS, agent."""
        listings: list[dict] = []
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            pm = PRICE_RE.search(line)
            if pm:
                try:
                    price = float(pm.group(1).replace(",", ""))

                    beds = baths = sqft = None
                    prop_type = "single_family"
                    addr = ""
                    mls_number = ""
                    agent_name = ""

                    days_on_market = None

                    for j in range(1, 25):
                        if i + j >= len(lines):
                            break
                        nl = lines[i + j].strip()
                        if not nl:
                            continue

                        # Beds: 3bds
                        if not beds:
                            bm = BEDS_RE.match(nl)
                            if bm:
                                beds = int(bm.group(1))
                                continue

                        # Baths: 2ba
                        if not baths:
                            bm = BATHS_RE.match(nl)
                            if bm:
                                baths = float(bm.group(1))
                                continue

                        # Sqft: 1,282sqft
                        if not sqft:
                            sm = SQFT_RE.search(nl)
                            if sm:
                                sqft = int(sm.group(1).replace(",", ""))
                                continue

                        # Property type: Apartment for sale, House for sale, etc.
                        if "for sale" in nl.lower() and nl[0].isalpha():
                            pt = nl.lower().split(" for sale")[0].strip()
                            type_map = {
                                "apartment": "condo", "condo": "condo", "house": "single_family",
                                "townhouse": "townhouse", "multi-family": "multi_family",
                                "land": "land", "mobile": "mobile"
                            }
                            for key, val in type_map.items():
                                if key in pt:
                                    prop_type = val
                                    continue

                        # MLS ID
                        if not mls_number:
                            mm = MLS_RE.search(nl)
                            if mm:
                                mls_number = mm.group(1)
                                # The agent/brokerage is after the MLS ID on the same line
                                after_mls = nl[mm.end():].strip().lstrip(",").strip()
                                if after_mls and not after_mls.startswith("MLS"):
                                    agent_name = after_mls

                        # Address: starts with a number, 10+ chars, contains street suffix
                        if not addr and nl[0].isdigit() and len(nl) > 12:
                            # Look for street suffix to confirm it's an address
                            street_suffixes = [
                                "St", "Ave", "Blvd", "Dr", "Cres", "Way", "Rd", "Pl",
                                "Ct", "Gate", "Heights", "Green", "Landing", "Rise",
                                "Row", "Place", "Park", "Gardens", "Circle", "Lane",
                                "Mews", "Trail", "Crossing", "Common", "Terrace",
                                "Point", "Bend", "Hill", "Grove", "Oaks", "Woods",
                                "Ridge", "Glen", "View", "Meadow", "Close", "Manor",
                            ]
                            if any(f" {sfx}" in nl or f" {sfx} " in nl for sfx in street_suffixes):
                                addr = nl.split(",")[0].strip()
                                # # skip the unit number suffix on second pass
                                if " #" in addr:
                                    addr = addr.split(" #")[0].strip()

                        # Days on market: "X hours ago", "X days ago", etc.
                        # Store raw hours so frontend can display 6h or 3d.
                        if days_on_market is None:
                            am = AGE_RE.search(nl)
                            if am:
                                num = int(am.group(1))
                                unit = am.group(2).lower()
                                if unit.startswith("hour"):
                                    days_on_market = num     # raw hours, < 24
                                elif unit.startswith("day"):
                                    days_on_market = num * 24  # convert to hours
                                elif unit.startswith("week"):
                                    days_on_market = num * 7 * 24
                                elif unit.startswith("month"):
                                    days_on_market = num * 30 * 24

                    if price and (beds or addr):
                        zpid = mls_number or str(abs(hash(addr))) if addr else ""
                        detail_url = f"https://www.zillow.com/homedetails/{zpid}_zpid/" if zpid else ""
                        listing = {
                            "address": addr or "Unknown",
                            "city": config.city or "",
                            "state": config.state or "",
                            "price": price,
                            "beds": beds,
                            "baths": baths,
                            "sqft": sqft,
                            "property_type": prop_type,
                            "status": "active",
                            "days_on_market": days_on_market,
                            "source": "zillow_web",
                            "source_listing_id": mls_number or zpid,
                            "source_url": detail_url,
                            "mls_number": mls_number,
                            "listing_agent_name": None,
                            "listing_brokerage": agent_name or None,
                            "description": None,
                            "photos": [],
                            "thumbnail_url": "",
                        }
                        listings.append(listing)
                except Exception:
                    pass

            i += 1

        return listings[:config.max_results]

    def _extract_images_from_html(self, html: str, listing_count: int) -> list[str]:
        """Extract listing photo URLs from Zillow HTML. Returns one thumbnail URL per listing.
        Deduplicates webp/jpg versions of same photo. Filters out logos and UI elements."""
        img_pattern = re.compile(
            r'(https://photos\.zillowstatic\.com/fp/[a-f0-9]+-[a-z]+_e\.(?:jpg|jpeg|webp))',
            re.IGNORECASE
        )
        all_urls = img_pattern.findall(html)

        # Deduplicate by hash (same photo in different formats)
        seen_hashes: set[str] = set()
        unique_photos: list[str] = []
        for url in all_urls:
            hash_match = re.search(r'/fp/([a-f0-9]+)', url)
            if hash_match and hash_match.group(1) not in seen_hashes:
                seen_hashes.add(hash_match.group(1))
                # Prefer jpg over webp
                if url.endswith(('.jpg', '.jpeg')):
                    unique_photos.insert(0, url) if url not in unique_photos else None
                else:
                    unique_photos.append(url)

        # Assign one thumbnail per listing
        return unique_photos[:listing_count] if unique_photos else []


    def _normalize_state_data(self, item: dict, config: PropertySearchConfig) -> dict:
        """Normalize a preloaded state dict into a standard listing dict."""
        img = item.get("imgSrc", "")
        if isinstance(img, dict):
            img = img.get("url", "")
        return {
            "address": item.get("address", item.get("streetAddress", "")),
            "city": item.get("addressCity", config.city or ""),
            "state": item.get("addressState", config.state or ""),
            "postal_code": item.get("addressZipcode", ""),
            "price": item.get("price") or item.get("unformattedPrice"),
            "beds": item.get("beds") or item.get("bedrooms"),
            "baths": item.get("baths") or item.get("bathrooms"),
            "sqft": item.get("area") or item.get("livingArea"),
            "property_type": (item.get("homeType") or "single_family").lower(),
            "status": "active",
            "source": "zillow_web",
            "source_listing_id": str(item.get("zpid", "")),
            "source_url": item.get("detailUrl", ""),
            "mls_number": item.get("mlsNumber", ""),
            "listing_brokerage": item.get("brokerName", ""),
            "photos": [img] if img else [],
            "thumbnail_url": img,
        }
