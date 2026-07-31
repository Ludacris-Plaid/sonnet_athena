"""
Source selection — either explicit (the user picks a source when
triggering an import, see routes_properties.py) or falling back to
settings.LISTINGS_SOURCE if none is specified.
"""
from app.core.config import settings
from app.scrapers.base import ListingsSource
from app.scrapers.demo_source import DemoListingsSource

SOURCE_META = {
    "demo": {
        "label": "Demo Data",
        "description": "Deterministic sample listings for testing — not real data.",
        "requires_config": False,
    },
    "reso": {
        "label": "MLS / RESO Web API",
        "description": "Direct feed from a licensed MLS via the RESO Web API standard. Requires an IDX/VOW data license from your local MLS board.",
        "requires_config": True,
    },
    "bridge": {
        "label": "Zillow (via Bridge Interactive)",
        "description": "Zillow Group's official RESO-standard data program — the legitimate path to Zillow-adjacent data. Requires approval as an MLS-affiliated brokerage or approved partner (bridgeinteractive.com/developers).",
        "requires_config": True,
    },
    "attom": {
        "label": "ATTOM Data",
        "description": "Licensed nationwide property and public-records data. Requires an ATTOM API key (developer.attomdata.com).",
        "requires_config": True,
    },
    "csv": {
        "label": "CSV Import",
        "description": "Upload a spreadsheet export — always available, no API key needed.",
        "requires_config": False,
    },
    "zillow_web": {
        "label": "Zillow (Web Scraper)",
        "description": "Headless scraping of public Zillow listings via Obscura stealth browser. Experimental.",
        "requires_config": True,
        "experimental": True,
        "requires_acceptance": True,
    },
    "realtor_com": {
        "label": "Realtor.com (HomeHarvest)",
        "description": "Scraped via HomeHarvest library (723 GitHub stars). Fetches MLS-style data including photos and agent info. US addresses only.",
        "requires_config": False,
        "experimental": True,
        "requires_acceptance": True,
    },
}


def get_listings_source(source_key: str | None = None, db=None, org_id: str | None = None) -> ListingsSource:
    key = source_key or settings.LISTINGS_SOURCE

    if key == "reso":
        from app.scrapers.reso_client import ResoListingsSource
        return ResoListingsSource()
    if key == "bridge":
        from app.scrapers.bridge_interactive import BridgeInteractiveSource
        return BridgeInteractiveSource()
    if key == "attom":
        from app.scrapers.attom_source import AttomDataSource
        return AttomDataSource()
    if key == "zillow_web":
        from app.scrapers.zillow_obscura import ZillowObscuraSource
        return ZillowObscuraSource()
    if key == "redfin_web":
        from app.scrapers.redfin_obscura import RedfinObscuraSource
        return RedfinObscuraSource()
    if key == "realtor_com":
        from app.scrapers.homeharvest_source import HomeHarvestSource
        return HomeHarvestSource()
    return DemoListingsSource()


def is_source_configured(key: str, db=None, org_id: str | None = None) -> bool:
    if key in ("demo", "csv", "zillow_web", "redfin_web", "realtor_com"):
        return True
    if db is not None and org_id is not None:
        from app.services.settings_service import get_effective_setting
        if key == "reso":
            return bool(get_effective_setting(db, org_id, "RESO_API_BASE_URL") and get_effective_setting(db, org_id, "RESO_API_TOKEN"))
        if key == "bridge":
            return bool(get_effective_setting(db, org_id, "BRIDGE_API_BASE_URL") and get_effective_setting(db, org_id, "BRIDGE_API_TOKEN"))
        if key == "attom":
            return bool(get_effective_setting(db, org_id, "ATTOM_API_KEY"))
        return False
    if key == "reso":
        return bool(settings.RESO_API_BASE_URL and settings.RESO_API_TOKEN)
    if key == "bridge":
        return bool(settings.BRIDGE_API_BASE_URL and settings.BRIDGE_API_TOKEN)
    if key == "attom":
        return bool(settings.ATTOM_API_KEY)
    return False


def list_available_sources(db=None, org_id: str | None = None) -> list[dict]:
    return [
        {"key": key, **meta, "configured": is_source_configured(key, db, org_id)}
        for key, meta in SOURCE_META.items()
    ]
