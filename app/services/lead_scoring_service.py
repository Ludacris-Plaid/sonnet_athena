"""
Deterministic engagement/staleness scoring — same pattern as
opportunity_service.py: compute a real number from real data, no LLM
guessing. Score components:
  - recency: how recently were they last contacted (fresher = higher)
  - frequency: how many messages in the last 30 days
  - qualification signals: pre-approved, has a budget set, has an active
    saved search
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.client import Client, SavedSearch
from app.models.message import Message

WEIGHTS = {"recency": 0.45, "frequency": 0.30, "qualification": 0.25}


def _recency_score(client: Client) -> float:
    if not client.last_contacted_at:
        return 20.0  # never contacted — some baseline, not zero, since they may just be new
    days_since = (datetime.now(timezone.utc) - client.last_contacted_at.replace(tzinfo=timezone.utc)).days
    if days_since <= 2:
        return 100.0
    if days_since >= 60:
        return 0.0
    return max(0.0, 100.0 - (days_since / 60.0) * 100.0)


def _frequency_score(db: Session, client: Client) -> float:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    count = db.query(Message).filter(Message.client_id == client.id, Message.created_at >= cutoff).count()
    return min(100.0, count * 15.0)  # 7+ messages in 30 days maxes this out


def _qualification_score(db: Session, client: Client) -> float:
    score = 0.0
    if client.pre_approved:
        score += 40
    if client.budget_max:
        score += 30
    has_active_search = db.query(SavedSearch).filter(SavedSearch.client_id == client.id, SavedSearch.is_active == True).first() is not None  # noqa: E712
    if has_active_search:
        score += 30
    return min(100.0, score)


def compute_engagement_score(db: Session, client: Client) -> float:
    recency = _recency_score(client)
    frequency = _frequency_score(db, client)
    qualification = _qualification_score(db, client)
    composite = recency * WEIGHTS["recency"] + frequency * WEIGHTS["frequency"] + qualification * WEIGHTS["qualification"]
    return round(composite, 1)


def recompute_and_save(db: Session, client: Client) -> Client:
    client.engagement_score = compute_engagement_score(db, client)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def get_stale_clients(db: Session, org_id: str, days: int = 14) -> list[Client]:
    """Clients not contacted in `days` — used by the STALE_LEAD alert rule."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    return (
        db.query(Client)
        .filter(
            Client.org_id == org_id,
            Client.status == "active",
            Client.do_not_contact == False,  # noqa: E712
            Client.pipeline_stage.notin_(["closed_won", "closed_lost"]),
        )
        .filter((Client.last_contacted_at == None) | (Client.last_contacted_at < cutoff))  # noqa: E711
        .all()
    )
