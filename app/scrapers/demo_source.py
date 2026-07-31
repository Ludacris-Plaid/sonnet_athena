"""
Deterministic sample-data generator standing in for a real, licensed data
feed (MLS/RESO Web API, ATTOM, Estated, etc.) during development and demos.

IMPORTANT: this does NOT scrape any live website. It exists so the rest of
the pipeline (property_service, analysis_service, embeddings, comps) can be
built and tested end-to-end before a licensed data source is wired in via
app/scrapers/reso_client.py.
"""
import hashlib
import random

from app.scrapers.base import ListingsSource

STREET_NAMES = ["Maple Ave", "9th St NW", "Riverbend Rd", "Oakmont Dr", "Whitemud Cres", "College Plaza"]
PROPERTY_TYPES = ["single_family", "condo", "townhouse", "multi_family"]
AGENT_FIRST_NAMES = ["Maria", "David", "Priya", "James", "Wei", "Fatima", "Connor", "Aisha"]
AGENT_LAST_NAMES = ["Nguyen", "Patel", "Kowalski", "Okafor", "Rossi", "Kim", "Fitzgerald", "Diaz"]
BROKERAGES = ["Summit Realty Group", "Riverstone Properties", "Northgate Real Estate", "Maple & Co. Realty"]


class DemoListingsSource(ListingsSource):
    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        # Seed on city+state so results are stable/repeatable per query, not random noise.
        seed = int(hashlib.sha256(f"{city}{state}".encode()).hexdigest(), 16) % (10**8)
        rng = random.Random(seed)

        listings = []
        for i in range(limit):
            beds = rng.randint(2, 6)
            sqft = rng.randint(700, 3200)
            base_price_per_sqft = rng.randint(180, 420)
            price = round(sqft * base_price_per_sqft, -3)

            # picsum.photos is a real, freely-usable placeholder image
            # service (not copyrighted listing photography) — seeded so
            # the same demo listing always shows the same images across
            # repeat ingestion runs, same determinism principle as the
            # rest of this generator.
            photo_seed = f"{seed}-{i}"
            photos = [f"https://picsum.photos/seed/{photo_seed}-{n}/800/600" for n in range(4)]

            agent_name = f"{rng.choice(AGENT_FIRST_NAMES)} {rng.choice(AGENT_LAST_NAMES)}"
            agent_email_handle = agent_name.lower().replace(" ", ".")

            listings.append(
                {
                    "address": f"{rng.randint(1000, 19999)} {rng.choice(STREET_NAMES)}",
                    "city": city,
                    "state": state,
                    "postal_code": None,
                    "latitude": None,
                    "longitude": None,
                    "price": float(price),
                    "beds": beds,
                    "baths": round(rng.uniform(1, beds), 1),
                    "sqft": sqft,
                    "property_type": rng.choice(PROPERTY_TYPES),
                    "year_built": rng.randint(1960, 2024),
                    "status": rng.choice(["active", "active", "active", "pending"]),
                    "days_on_market": rng.randint(1, 120),
                    "description": f"{beds} bed, {sqft} sqft home in {city}, {state}",
                    "thumbnail_url": photos[0],
                    "photos": photos,
                    "mls_number": f"MLS{seed}{i:03d}",
                    "lot_size_sqft": rng.randint(sqft, sqft * 4),
                    "garage_spaces": rng.randint(0, 3),
                    "listing_agent_name": agent_name,
                    "listing_agent_email": f"{agent_email_handle}@example-realty.com",
                    "listing_agent_phone": f"555-{rng.randint(100,999)}-{rng.randint(1000,9999)}",
                    "listing_brokerage": rng.choice(BROKERAGES),
                    "source": "demo",
                    "source_listing_id": f"demo-{seed}-{i}",
                    "source_url": None,
                    "raw_data": None,
                }
            )
        return listings
