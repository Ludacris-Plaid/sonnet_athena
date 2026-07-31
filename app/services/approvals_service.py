"""
Aggregates everything currently waiting on a human decision into one list —
draft messages awaiting send, unread high-severity compliance flags, and
failed CRM syncs needing attention. Inspired by Meridian Company OS's
"pending approvals" surface on its operator cockpit (see the provenance
note in command_parser_service.py — built from the described concept, not
copied code, since the source repo wasn't accessible when this was built).

Deliberately read-only aggregation over existing tables — no new "approval"
table, since everything here already has its own real state (Message,
AlertEvent, CRMSyncLog) and duplicating that into a parallel model would
just create a sync problem.
"""
from sqlalchemy.orm import Session

from app.models.message import Message, MessageDirection
from app.models.alert import AlertEvent, AlertRule
from app.models.crm_connection import CRMConnection, CRMSyncLog


def get_pending_approvals(db: Session, org_id: str) -> list[dict]:
    items = []

    # Inbound messages with drafts generated but no reply sent yet.
    pending_drafts = (
        db.query(Message)
        .filter(Message.org_id == org_id, Message.direction == MessageDirection.INBOUND, Message.draft_replies.isnot(None))
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    for m in pending_drafts:
        items.append(
            {
                "type": "draft_reply",
                "priority": "normal",
                "summary": f"Reply needed: {m.channel.value} from {m.from_address or 'unknown'}",
                "created_at": m.created_at.isoformat(),
                "ref_id": str(m.id),
            }
        )

    # Unread critical/warning compliance alerts.
    flagged_events = (
        db.query(AlertEvent)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .filter(AlertRule.org_id == org_id, AlertEvent.is_read == False, AlertEvent.severity.in_(["critical", "warning"]))  # noqa: E712
        .order_by(AlertEvent.created_at.desc())
        .limit(20)
        .all()
    )
    for e in flagged_events:
        items.append(
            {
                "type": "compliance_alert",
                "priority": "high" if e.severity == "critical" else "normal",
                "summary": e.headline,
                "created_at": e.created_at.isoformat(),
                "ref_id": str(e.id),
            }
        )

    # CRM connections whose last sync failed.
    failed_connections = db.query(CRMConnection).filter(CRMConnection.org_id == org_id, CRMConnection.last_sync_status == "error").all()
    for c in failed_connections:
        items.append(
            {
                "type": "crm_sync_error",
                "priority": "normal",
                "summary": f"{c.provider.value} sync failed — needs attention",
                "created_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                "ref_id": str(c.id),
            }
        )

    items.sort(key=lambda x: (x["priority"] != "high", x["created_at"] or ""), reverse=False)
    return items
