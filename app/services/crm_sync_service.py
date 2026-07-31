"""
Syncs contacts between a connected CRM and RealtyAI's Client table.
Matching on repeat syncs is by (external_provider, external_id) — never by
name/email alone, to avoid silently merging two different people who
happen to share an email typo or a common name.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crm_connection import CRMConnection, CRMSyncLog, SyncDirection
from app.crm_connectors.factory import get_connector
from app.services.crm_credential_service import decrypt_credentials


def run_sync(db: Session, connection: CRMConnection, trigger: str = "manual") -> CRMSyncLog:
    log = CRMSyncLog(connection_id=connection.id, trigger=trigger, status="running")
    db.add(log)
    db.commit()
    db.refresh(log)

    try:
        credentials = decrypt_credentials(connection.encrypted_credentials)
        connector = get_connector(connection.provider.value, credentials)

        imported = updated = exported = 0

        if connection.sync_direction in (SyncDirection.IMPORT_ONLY, SyncDirection.TWO_WAY):
            since = connection.last_synced_at.isoformat() if connection.last_synced_at else None
            remote_contacts = connector.list_contacts(since=since)
            for contact in remote_contacts:
                created = _upsert_client_from_contact(db, connection, contact)
                if created:
                    imported += 1
                else:
                    updated += 1

        if connection.sync_direction in (SyncDirection.EXPORT_ONLY, SyncDirection.TWO_WAY):
            unsynced_clients = (
                db.query(Client)
                .filter(Client.org_id == connection.org_id, Client.external_provider.is_(None))
                .all()
            )
            for client_row in unsynced_clients:
                contact = _client_to_contact(client_row)
                external_id = connector.create_or_update_contact(contact)
                client_row.external_provider = connection.provider.value
                client_row.external_id = external_id
                client_row.last_synced_at = datetime.now(timezone.utc)
                db.add(client_row)
                exported += 1

        db.commit()

        log.status = "success"
        log.contacts_imported = imported
        log.contacts_updated = updated
        log.contacts_exported = exported
        connection.last_synced_at = datetime.now(timezone.utc)
        connection.last_sync_status = "success"

    except Exception as e:  # noqa: BLE001 — sync failures must be recorded, not propagated as a 500
        db.rollback()
        log.status = "error"
        log.error_message = str(e)
        connection.last_sync_status = "error"

    log.finished_at = datetime.now(timezone.utc)
    db.add(log)
    db.add(connection)
    db.commit()
    db.refresh(log)
    return log


def handle_webhook_contact_update(db: Session, connection: CRMConnection, contact_ref: dict) -> None:
    """
    Called once per contact reference extracted from a webhook payload.
    Most providers' webhooks only include an ID, not the full record — so
    this fetches the current record via the connector before upserting.
    """
    credentials = decrypt_credentials(connection.encrypted_credentials)
    connector = get_connector(connection.provider.value, credentials)

    if not hasattr(connector, "fetch_contact_by_id"):
        return
    full_contact = connector.fetch_contact_by_id(contact_ref["external_id"])
    if full_contact:
        _upsert_client_from_contact(db, connection, full_contact)
        db.commit()


def _upsert_client_from_contact(db: Session, connection: CRMConnection, contact: dict) -> bool:
    """Returns True if a new Client was created, False if an existing one was updated."""
    existing = (
        db.query(Client)
        .filter(
            Client.org_id == connection.org_id,
            Client.external_provider == connection.provider.value,
            Client.external_id == contact["external_id"],
        )
        .first()
    )

    if existing:
        existing.name = contact.get("name") or existing.name
        existing.email = contact.get("email") or existing.email
        existing.phone = contact.get("phone") or existing.phone
        existing.client_type = contact.get("client_type") or existing.client_type
        existing.budget_max = contact.get("budget_max") or existing.budget_max
        existing.preferred_city = contact.get("preferred_city") or existing.preferred_city
        existing.last_synced_at = datetime.now(timezone.utc)
        db.add(existing)
        return False

    new_client = Client(
        org_id=connection.org_id,
        owning_user_id=connection.user_id,
        name=contact.get("name", "Unknown"),
        email=contact.get("email"),
        phone=contact.get("phone"),
        client_type=contact.get("client_type", "buyer"),
        external_provider=connection.provider.value,
        external_id=contact["external_id"],
        budget_max=contact.get("budget_max"),
        preferred_city=contact.get("preferred_city"),
        last_synced_at=datetime.now(timezone.utc),
    )
    db.add(new_client)
    return True


def _client_to_contact(client_row: Client) -> dict:
    return {
        "external_id": client_row.external_id,
        "name": client_row.name,
        "email": client_row.email,
        "phone": client_row.phone,
        "client_type": client_row.client_type,
        "budget_max": client_row.budget_max,
        "preferred_city": client_row.preferred_city,
    }
