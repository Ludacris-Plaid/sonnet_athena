"""
CSV property import — the always-available fallback alongside the API
sources, same reasoning as the CRM CSV import: not every agent has MLS
access or an ATTOM/Bridge subscription, and a spreadsheet export from
wherever they're currently tracking listings should always work.
"""
import csv
import io

from sqlalchemy.orm import Session

from app.models.property import Property

COLUMN_ALIASES = {
    "address": ["address", "street address", "property address"],
    "city": ["city"],
    "state": ["state", "province"],
    "price": ["price", "list price", "asking price"],
    "beds": ["beds", "bedrooms"],
    "baths": ["baths", "bathrooms"],
    "sqft": ["sqft", "square feet", "sq ft"],
    "property_type": ["type", "property type"],
    "listing_agent_name": ["agent", "listing agent", "agent name"],
    "listing_agent_email": ["agent email"],
    "listing_agent_phone": ["agent phone"],
}


def _find_column(header: list[str], candidates: list[str]) -> str | None:
    lowered = {h.lower().strip(): h for h in header}
    for c in candidates:
        if c in lowered:
            return lowered[c]
    return None


def _to_float(val: str) -> float | None:
    if not val:
        return None
    digits = "".join(c for c in val if c.isdigit() or c == ".")
    return float(digits) if digits else None


def import_csv(db: Session, org_id: str, file_bytes: bytes) -> dict:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    col_map = {field: _find_column(header, aliases) for field, aliases in COLUMN_ALIASES.items()}

    created = 0
    skipped = 0
    for row in reader:
        address = row.get(col_map["address"], "").strip() if col_map["address"] else ""
        if not address:
            skipped += 1
            continue

        db.add(Property(
            org_id=org_id,
            address=address,
            city=row.get(col_map["city"], "").strip() if col_map["city"] else "",
            state=row.get(col_map["state"], "").strip() if col_map["state"] else "",
            price=_to_float(row.get(col_map["price"], "")) if col_map["price"] else None,
            beds=int(_to_float(row.get(col_map["beds"], "0")) or 0) if col_map["beds"] else None,
            baths=_to_float(row.get(col_map["baths"], "")) if col_map["baths"] else None,
            sqft=int(_to_float(row.get(col_map["sqft"], "0")) or 0) if col_map["sqft"] else None,
            property_type=row.get(col_map["property_type"], "").strip() if col_map["property_type"] else None,
            listing_agent_name=row.get(col_map["listing_agent_name"], "").strip() or None if col_map["listing_agent_name"] else None,
            listing_agent_email=row.get(col_map["listing_agent_email"], "").strip() or None if col_map["listing_agent_email"] else None,
            listing_agent_phone=row.get(col_map["listing_agent_phone"], "").strip() or None if col_map["listing_agent_phone"] else None,
            source="csv",
            status="active",
        ))
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped}
