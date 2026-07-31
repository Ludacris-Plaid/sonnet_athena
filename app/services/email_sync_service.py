"""
Imports messages from a connected mailbox into the unified Message table
(same table the whole inbox/trust-ladder/compliance system already uses —
imported emails get all of that for free, no separate "imported email"
concept needed).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.email_connection import EmailConnection, EmailProvider
from app.models.message import Message, Channel, MessageDirection
from app.email_connectors.gmail import GmailConnector
from app.email_connectors.microsoft import MicrosoftEmailConnector


def _get_connector(connection: EmailConnection):
    if connection.provider == EmailProvider.GMAIL:
        return GmailConnector(connection.encrypted_tokens)
    return MicrosoftEmailConnector(connection.encrypted_tokens)


def sync_connection(db: Session, connection: EmailConnection) -> dict:
    connector = _get_connector(connection)

    if connection.provider == EmailProvider.GMAIL:
        messages, new_cursor = connector.list_new_messages(history_id=connection.history_id)
    else:
        messages, new_cursor = connector.list_new_messages(delta_link=connection.delta_link)

    imported = 0
    for m in messages:
        existing = (
            db.query(Message)
            .filter(Message.org_id == connection.org_id, Message.from_address == m.get("from_address"), Message.subject == m.get("subject"), Message.body == m.get("body"))
            .first()
        )
        if existing:
            continue  # crude dedup — good enough given Gmail/Graph already dedupe by their own IDs upstream in most cases
        db.add(Message(
            org_id=connection.org_id, user_id=connection.user_id,
            channel=Channel.EMAIL, direction=MessageDirection.INBOUND,
            from_address=m.get("from_address"), to_address=m.get("to_address"),
            subject=m.get("subject"), body=m.get("body") or "(no content)",
        ))
        imported += 1

    if connection.provider == EmailProvider.GMAIL:
        connection.history_id = new_cursor
    else:
        connection.delta_link = new_cursor

    connection.last_synced_at = datetime.now(timezone.utc)
    connection.last_sync_status = "success"
    if connector.refreshed_tokens:
        connection.encrypted_tokens = connector.refreshed_tokens
    db.add(connection)
    db.commit()

    return {"imported": imported}
