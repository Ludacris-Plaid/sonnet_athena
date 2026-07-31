"""
Connects the compliance layer to the alerts system: whenever an outbound
message ends up compliance_flagged, this raises a real AlertEvent instead
of the flag sitting silently on the message row.

Modeled as an always-on "system rule" (AlertRuleType.COMPLIANCE_FLAG,
is_system=True) rather than a special-cased notification path — this keeps
one consistent mental model ("alerts come from rules") instead of two, and
means the existing GET /alerts/events endpoint, unread counts, and future
delivery channels (SMS/push) all pick this up for free without needing
compliance-specific handling anywhere else.
"""
from sqlalchemy.orm import Session

from app.models.alert import AlertRule, AlertEvent, AlertRuleType
from app.models.message import Message

CHANNEL_LABELS = {"email": "an email", "sms": "a text", "voice": "a voice reply", "slack": "a Slack message", "manual": "a message"}


def get_or_create_compliance_rule(db: Session, org_id: str, user_id: str) -> AlertRule:
    rule = (
        db.query(AlertRule)
        .filter(AlertRule.org_id == org_id, AlertRule.user_id == user_id, AlertRule.rule_type == AlertRuleType.COMPLIANCE_FLAG)
        .first()
    )
    if rule:
        return rule

    rule = AlertRule(org_id=org_id, user_id=user_id, rule_type=AlertRuleType.COMPLIANCE_FLAG, is_active=True, is_system=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def raise_compliance_alert(db: Session, org_id: str, user_id: str, message: Message) -> AlertEvent:
    """
    Call this right after any outbound Message is saved with
    compliance_flagged=True. Voice replies (which send with no human review)
    are marked "critical"; email/SMS (where a human already saw and chose
    to send anyway) are marked "warning" — same severity distinction the
    compliance gate itself makes between blocking voice vs. informing email/SMS.
    """
    rule = get_or_create_compliance_rule(db, org_id, user_id)

    channel_label = CHANNEL_LABELS.get(message.channel.value, "a message")
    severity = "critical" if message.channel.value == "voice" else "warning"

    event = AlertEvent(
        rule_id=rule.id,
        message_id=message.id,
        headline=f"Compliance flag on {channel_label}",
        detail=message.compliance_notes or "Flagged by the fair housing screener — review the message content.",
        severity=severity,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
