from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.alert import AlertRule, AlertEvent, AlertRuleType

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertRuleCreate(BaseModel):
    rule_type: AlertRuleType
    client_id: str | None = None
    params: dict = {}


@router.post("/rules")
def create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rule = AlertRule(
        org_id=user.org_id,
        user_id=user.id,
        client_id=payload.client_id,
        rule_type=payload.rule_type,
        params=payload.params,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(AlertRule).filter(AlertRule.org_id == user.org_id).all()


@router.get("/events")
def list_events(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = (
        db.query(AlertEvent)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .filter(AlertRule.org_id == user.org_id)
    )
    if unread_only:
        query = query.filter(AlertEvent.is_read == False)  # noqa: E712
    return query.order_by(AlertEvent.created_at.desc()).limit(100).all()


@router.get("/events/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Lightweight endpoint for a sidebar notification badge — avoids
    fetching the full event list just to get a number."""
    count = (
        db.query(AlertEvent)
        .join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        .filter(AlertRule.org_id == user.org_id, AlertEvent.is_read == False)  # noqa: E712
        .count()
    )
    return {"unread_count": count}


@router.post("/events/{event_id}/read")
def mark_read(event_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.query(AlertEvent).filter(AlertEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.is_read = True
    db.add(event)
    db.commit()
    return {"ok": True}
