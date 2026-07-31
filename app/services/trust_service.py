"""
Implements the trust ladder: Athena starts draft-only for every action type
and earns autonomy per-user, per-action-type based on logged outcomes.

Scoring (simple, tunable):
  sent unedited  -> +3
  edited by user -> +0.5   (still useful signal, weak positive)
  rejected       -> -8     (strong negative, autonomy should not creep up on bad drafts)

Score is clamped to [0, 100]. Automation level is derived from thresholds
in settings, so it can be tuned per-deployment without code changes.
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.trust import TrustScore, TrustEvent, ActionType, AutomationLevel

SCORE_DELTAS = {
    "sent_unedited": 3.0,
    "edited": 0.5,
    "rejected": -8.0,
}


def _level_for_score(score: float) -> AutomationLevel:
    if score >= settings.TRUST_THRESHOLD_AUTONOMOUS:
        return AutomationLevel.FULL_AUTONOMY
    if score >= settings.TRUST_THRESHOLD_LIMITED:
        return AutomationLevel.LIMITED_AUTONOMY
    return AutomationLevel.DRAFT_ONLY


def get_or_create_trust_score(db: Session, user_id: str, action_type: ActionType) -> TrustScore:
    ts = (
        db.query(TrustScore)
        .filter(TrustScore.user_id == user_id, TrustScore.action_type == action_type)
        .first()
    )
    if ts:
        return ts
    ts = TrustScore(user_id=user_id, action_type=action_type, score=0.0)
    db.add(ts)
    db.commit()
    db.refresh(ts)
    return ts


def record_outcome(
    db: Session,
    user_id: str,
    action_type: ActionType,
    outcome: str,  # "sent_unedited" | "edited" | "rejected"
    related_message_id: str | None = None,
) -> TrustScore:
    ts = get_or_create_trust_score(db, user_id, action_type)

    delta = SCORE_DELTAS.get(outcome, 0.0)
    new_score = max(0.0, min(100.0, ts.score + delta))

    ts.score = new_score
    ts.total_actions += 1
    if outcome == "sent_unedited":
        ts.actions_sent_unedited += 1
    elif outcome == "edited":
        ts.actions_edited += 1
    elif outcome == "rejected":
        ts.actions_rejected += 1
    ts.automation_level = _level_for_score(new_score)

    event = TrustEvent(
        user_id=user_id,
        action_type=action_type,
        outcome=outcome,
        score_delta=delta,
        resulting_score=new_score,
        related_message_id=related_message_id,
    )
    db.add(event)
    db.add(ts)
    db.commit()
    db.refresh(ts)
    return ts


def can_act_autonomously(db: Session, user_id: str, action_type: ActionType) -> bool:
    ts = get_or_create_trust_score(db, user_id, action_type)
    return ts.automation_level == AutomationLevel.FULL_AUTONOMY


def can_act_with_limited_autonomy(db: Session, user_id: str, action_type: ActionType) -> bool:
    ts = get_or_create_trust_score(db, user_id, action_type)
    return ts.automation_level in (AutomationLevel.LIMITED_AUTONOMY, AutomationLevel.FULL_AUTONOMY)
