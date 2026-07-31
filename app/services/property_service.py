"""
Property ingestion + comps retrieval.

Ingestion is upsert-aware: re-running ingestion for a city updates existing
properties (matched on source + source_listing_id) rather than duplicating
them, and records a PriceHistory row on every change. This is what makes
real price-drop detection (the Opportunity Engine, Alerts) possible instead
of guessed.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.property import Property
from app.models.comparable import Comparable
from app.models.price_history import PriceHistory
from app.scrapers.factory import get_listings_source
from app.memory.vector_store import vector_store
from app.services.compliance_service import keyword_risk_summary


def ingest_listings(db: Session, org_id: str, city: str, state: str, limit: int = 50, source_key: str | None = None) -> list[Property]:
    source = get_listings_source(source_key, db, org_id)
    raw_listings = source.fetch_listings(city=city, state=state, limit=limit)

    touched: list[Property] = []
    newly_created: list[Property] = []

    for item in raw_listings:
        # Fast keyword-only compliance check, run on every listing whether
        # new or updated — no LLM call here so bulk ingestion stays quick.
        # Agents can request a deeper LLM-backed review on demand via
        # POST /properties/{id}/compliance-check.
        description = item.get("description") or ""
        if description:
            risk_summary = keyword_risk_summary(description)
            item["compliance_risk"] = risk_summary["risk"]
            item["compliance_flags"] = risk_summary["flags"]

        existing = None
        if item.get("source_listing_id"):
            existing = (
                db.query(Property)
                .filter(
                    Property.org_id == org_id,
                    Property.source == item.get("source"),
                    Property.source_listing_id == item.get("source_listing_id"),
                )
                .first()
            )

        if existing:
            price_changed = existing.price != item.get("price")
            for key, value in item.items():
                setattr(existing, key, value)
            db.add(existing)
            if price_changed:
                db.add(PriceHistory(property_id=existing.id, price=item.get("price")))
            touched.append(existing)
        else:
            prop = Property(org_id=org_id, **item)
            db.add(prop)
            touched.append(prop)
            newly_created.append(prop)

    db.commit()
    for p in touched:
        db.refresh(p)
        if not db.query(PriceHistory).filter(PriceHistory.property_id == p.id).first():
            db.add(PriceHistory(property_id=p.id, price=p.price))
    db.commit()

    # Index only newly created properties for semantic comp search (existing
    # ones were already indexed on their first ingestion).
    for p in newly_created:
        text = f"{p.address}, {p.city}, {p.state}. {p.beds}bd/{p.baths}ba, {p.sqft}sqft, {p.property_type}. {p.description or ''}"
        vector_store.add(text, {"org_id": str(org_id), "category": "property", "property_id": str(p.id)})

    return touched


def find_comps(db: Session, subject: Property, max_comps: int = 5) -> list[dict]:
    query_text = (
        f"{subject.beds}bd/{subject.baths}ba, {subject.sqft}sqft, "
        f"{subject.property_type} in {subject.city}, {subject.state}"
    )

    def _filter(meta: dict) -> bool:
        return (
            meta.get("category") == "property"
            and meta.get("org_id") == str(subject.org_id)
            and meta.get("property_id") != str(subject.id)
        )

    matches = vector_store.search(query_text, top_k=max_comps, filter_fn=_filter)

    comps = []
    for m in matches:
        comp_property = db.query(Property).filter(Property.id == uuid.UUID(m["property_id"])).first()
        if not comp_property or not comp_property.price or not comp_property.sqft:
            continue
        subject_pps = (subject.price or 0) / subject.sqft if subject.sqft else 0
        comp_pps = comp_property.price / comp_property.sqft
        comps.append(
            {
                "id": comp_property.id,
                "address": comp_property.address,
                "price": comp_property.price,
                "beds": comp_property.beds,
                "baths": comp_property.baths,
                "sqft": comp_property.sqft,
                "days_on_market": comp_property.days_on_market,
                "similarity_score": m["score"],
                "price_per_sqft_delta": round(comp_pps - subject_pps, 2) if subject_pps else None,
            }
        )

    for c in comps:
        db.add(
            Comparable(
                subject_property_id=subject.id,
                comp_property_id=c["id"],
                similarity_score=c["similarity_score"],
                price_per_sqft_delta=c.get("price_per_sqft_delta"),
            )
        )
    db.commit()

    return comps
