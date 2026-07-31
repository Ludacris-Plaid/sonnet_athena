"""
Opportunity Engine: scores active listings on how much they deviate from
normal market behavior, using only data already in the database (price
history, city-level price-per-sqft distribution, days on market).

This intentionally does NOT use owner-equity, ownership-length, or any
personal/OSINT signal about the seller — everything here is standard,
publicly-listed comparative market data, the same inputs any realtor
already uses for a CMA. It's just automated and run across every listing
instead of one at a time.

Score components (each 0-100, weighted):
  - price_position: how cheap is this vs. comparable active listings, by $/sqft
  - dom_pressure: how much longer than average has it sat (signals room to negotiate)
  - price_drop: has the price been cut since first ingested, and by how much
"""
import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.property import Property
from app.models.price_history import PriceHistory

WEIGHTS = {"price_position": 0.45, "dom_pressure": 0.25, "price_drop": 0.30}


def _price_position_score(subject: Property, peers: list[Property]) -> float:
    if not subject.price or not subject.sqft:
        return 0.0
    peer_pps = [p.price / p.sqft for p in peers if p.price and p.sqft and p.id != subject.id]
    if len(peer_pps) < 3:
        return 50.0  # not enough peers to judge confidently — neutral score
    median_pps = statistics.median(peer_pps)
    subject_pps = subject.price / subject.sqft
    if median_pps == 0:
        return 50.0
    # Cheaper than median -> higher score. Cap the swing at +/-40 points around 50.
    pct_below_median = (median_pps - subject_pps) / median_pps
    return max(0.0, min(100.0, 50 + pct_below_median * 200))


def _dom_pressure_score(subject: Property, peers: list[Property]) -> float:
    if subject.days_on_market is None:
        return 50.0
    peer_doms = [p.days_on_market for p in peers if p.days_on_market is not None and p.id != subject.id]
    if len(peer_doms) < 3:
        return 50.0
    avg_dom = statistics.mean(peer_doms)
    if avg_dom == 0:
        return 50.0
    ratio = subject.days_on_market / avg_dom
    return max(0.0, min(100.0, (ratio - 1) * 60 + 50))


def price_drop_score(db: Session, subject: Property) -> tuple[float, float | None]:
    history = (
        db.query(PriceHistory)
        .filter(PriceHistory.property_id == subject.id)
        .order_by(PriceHistory.recorded_at.asc())
        .all()
    )
    if len(history) < 2:
        return 0.0, None
    first_price = history[0].price
    latest_price = history[-1].price
    if not first_price:
        return 0.0, None
    drop_pct = (first_price - latest_price) / first_price * 100
    if drop_pct <= 0:
        return 0.0, drop_pct
    # A 10% drop maxes the score
    return max(0.0, min(100.0, drop_pct * 10)), drop_pct


def score_opportunities(db: Session, org_id: str, city: str, min_score: float = 0, limit: int = 25) -> list[dict]:
    listings = (
        db.query(Property)
        .filter(Property.org_id == org_id, Property.city == city, Property.status == "active")
        .all()
    )
    if not listings:
        return []

    results = []
    for subject in listings:
        peers = [p for p in listings if p.property_type == subject.property_type]
        price_score = _price_position_score(subject, peers)
        dom_score = _dom_pressure_score(subject, peers)
        drop_score, drop_pct = price_drop_score(db, subject)

        composite = (
            price_score * WEIGHTS["price_position"]
            + dom_score * WEIGHTS["dom_pressure"]
            + drop_score * WEIGHTS["price_drop"]
        )

        if composite < min_score:
            continue

        results.append(
            {
                "property_id": subject.id,
                "address": subject.address,
                "price": subject.price,
                "beds": subject.beds,
                "sqft": subject.sqft,
                "days_on_market": subject.days_on_market,
                "opportunity_score": round(composite, 1),
                "price_position_score": round(price_score, 1),
                "dom_pressure_score": round(dom_score, 1),
                "price_drop_score": round(drop_score, 1),
                "price_drop_pct": round(drop_pct, 1) if drop_pct else None,
            }
        )

    results.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return results[:limit]
