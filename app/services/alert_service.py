"""
Evaluates active AlertRules against a freshly-ingested batch of properties
and creates AlertEvent rows. Call this right after property_service.ingest_listings
in the same request/job so alerts are generated from real, fresh data.

evaluate_stale_lead_alerts() is separate — it's time-based, not triggered
by an ingestion batch, so it's called on-demand (see routes_clients.py) or
should be wired to a scheduled job (cron/Celery beat) in production for
real "zero setup" behavior rather than requiring an agent to remember to
click a button.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.alert import AlertRule, AlertEvent, AlertRuleType
from app.models.property import Property
from app.models.client import Client
from app.services.opportunity_service import price_drop_score
from app.services.matching_service import match_score
from app.services.lead_scoring_service import get_stale_clients


def evaluate_alerts_for_batch(db: Session, org_id: str, touched_properties: list[Property]) -> list[AlertEvent]:
    rules = db.query(AlertRule).filter(AlertRule.org_id == org_id, AlertRule.is_active == True).all()  # noqa: E712
    events: list[AlertEvent] = []

    for rule in rules:
        params = rule.params or {}

        if rule.rule_type == AlertRuleType.PRICE_DROP_PCT:
            threshold = params.get("threshold_pct", 5)
            for prop in touched_properties:
                _, drop_pct = price_drop_score(db, prop)
                if drop_pct and drop_pct >= threshold:
                    events.append(
                        _create_event(
                            db,
                            rule,
                            prop,
                            headline=f"Price dropped {drop_pct:.1f}% — {prop.address}",
                            detail=f"Now ${prop.price:,.0f}",
                        )
                    )

        elif rule.rule_type == AlertRuleType.LONG_DOM:
            dom_threshold = params.get("dom_days", 60)
            for prop in touched_properties:
                if prop.days_on_market and prop.days_on_market >= dom_threshold:
                    events.append(
                        _create_event(
                            db,
                            rule,
                            prop,
                            headline=f"{prop.address} has been listed {prop.days_on_market} days",
                            detail="Possible negotiation opportunity — well above typical days on market.",
                        )
                    )

        elif rule.rule_type == AlertRuleType.NEW_LISTING_MATCH:
            if not rule.client_id:
                continue
            client = db.query(Client).filter(Client.id == rule.client_id).first()
            if not client:
                continue
            for prop in touched_properties:
                score = match_score(client, prop)
                if score >= params.get("min_match_score", 70):
                    events.append(
                        _create_event(
                            db,
                            rule,
                            prop,
                            headline=f"New match for {client.name}: {prop.address}",
                            detail=f"${prop.price:,.0f} · match score {score:.0f}",
                        )
                    )

    db.commit()
    return events


def evaluate_stale_lead_alerts(db: Session, org_id: str) -> list[AlertEvent]:
    """
    Checks all active STALE_LEAD rules for the org against
    lead_scoring_service.get_stale_clients(). Dedups against the last 7
    days so the same stale client doesn't re-alert every single call —
    important since this is meant to be safe to call frequently (or on a
    schedule) without spamming the agent.
    """
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.org_id == org_id, AlertRule.is_active == True, AlertRule.rule_type == AlertRuleType.STALE_LEAD)  # noqa: E712
        .all()
    )
    events: list[AlertEvent] = []
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for rule in rules:
        days_threshold = (rule.params or {}).get("stale_days", 14)
        stale_clients = get_stale_clients(db, org_id, days=days_threshold)

        for client in stale_clients:
            already_alerted = (
                db.query(AlertEvent)
                .filter(AlertEvent.rule_id == rule.id, AlertEvent.client_id == client.id, AlertEvent.created_at >= dedup_cutoff)
                .first()
            )
            if already_alerted:
                continue

            last_contact_desc = client.last_contacted_at.strftime("%b %d") if client.last_contacted_at else "never"
            event = AlertEvent(
                rule_id=rule.id,
                client_id=client.id,
                headline=f"{client.name} hasn't been contacted in a while",
                detail=f"Last contact: {last_contact_desc}. Pipeline stage: {client.pipeline_stage}.",
                severity="warning",
            )
            db.add(event)
            events.append(event)

    db.commit()
    return events


def _create_event(db: Session, rule: AlertRule, prop: Property, headline: str, detail: str) -> AlertEvent:
    event = AlertEvent(rule_id=rule.id, property_id=prop.id, headline=headline, detail=detail)
    db.add(event)
    return event
