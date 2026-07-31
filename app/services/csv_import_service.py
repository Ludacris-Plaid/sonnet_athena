"""
Handles the CSV import path — separate from crm_sync_service since it's a
one-time file import, not a live connector sync (see csv_connector.py for
why). Reuses the same upsert logic conceptually but matched differently:
CSV rows have no external_id, so matching is best-effort on email (when
present) to avoid obvious duplicates on repeat imports of overlapping
exports, falling back to always-create when there's no email to match on.
"""
from sqlalchemy.orm import Session

from app.models.client import Client
from app.crm_connectors.csv_connector import parse_csv_contacts


def import_csv(db: Session, org_id: str, user_id: str, file_bytes: bytes) -> dict:
    contacts = parse_csv_contacts(file_bytes)

    created = 0
    updated = 0
    skipped = 0

    for contact in contacts:
        existing = None
        if contact.get("email"):
            existing = (
                db.query(Client)
                .filter(Client.org_id == org_id, Client.email == contact["email"])
                .first()
            )

        if existing:
            existing.name = contact["name"] or existing.name
            existing.phone = contact.get("phone") or existing.phone
            existing.budget_max = contact.get("budget_max") or existing.budget_max
            existing.preferred_city = contact.get("preferred_city") or existing.preferred_city
            db.add(existing)
            updated += 1
        else:
            db.add(
                Client(
                    org_id=org_id,
                    owning_user_id=user_id,
                    name=contact["name"],
                    email=contact.get("email"),
                    phone=contact.get("phone"),
                    client_type=contact.get("client_type", "buyer"),
                    budget_max=contact.get("budget_max"),
                    preferred_city=contact.get("preferred_city"),
                    external_provider="csv",
                )
            )
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total_rows": len(contacts)}
