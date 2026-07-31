"""
Gamification layer on top of the trust ladder: levels/tiers, badges, and
actionable hints for increasing trust. Deterministic — every badge and
level is computed from real TrustScore/TrustEvent/compliance data, nothing
fabricated for effect. That matters here specifically: the whole point of
this feature is to make the trust system feel legible and motivating,
which only works if a badge always corresponds to something real Athena
actually did.

Levels are aligned to the SAME thresholds that gate real autonomy
(TRUST_THRESHOLD_LIMITED, TRUST_THRESHOLD_AUTONOMOUS in config.py) so the
gamified level always matches what Athena can actually do — no "Level 4"
that doesn't correspond to any real capability change.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.trust import TrustScore, TrustEvent, TrustBadge, ActionType
from app.models.message import Message

LEVELS = [
    {"key": "new_partnership", "name": "New Partnership", "min_score": 0, "icon": "🌱", "color": "#8a8577"},
    {"key": "building_rapport", "name": "Building Rapport", "min_score": 20, "icon": "🤝", "color": "#7c8c64"},
    {"key": "limited_trust", "name": "Limited Trust Earned", "min_score": settings.TRUST_THRESHOLD_LIMITED, "icon": "🔓", "color": "#c99a3e"},
    {"key": "strong_trust", "name": "Strong Trust", "min_score": 60, "icon": "⚡", "color": "#a97f2e"},
    {"key": "full_autonomy", "name": "Full Autonomy", "min_score": settings.TRUST_THRESHOLD_AUTONOMOUS, "icon": "👑", "color": "#4f7a4a"},
]

BADGE_DEFINITIONS = {
    "first_steps": {
        "label": "First Steps", "icon": "🌱", "color": "olive",
        "description": "Athena sent her first message on your behalf.",
    },
    "quick_draw": {
        "label": "Quick Draw", "icon": "⚡", "color": "gold",
        "description": "10 replies sent exactly as drafted, no edits needed.",
    },
    "prolific": {
        "label": "Prolific", "icon": "📈", "color": "olive",
        "description": "50 total actions logged across all channels.",
    },
    "unlocked_limited": {
        "label": "Trusted Voice", "icon": "🔓", "color": "gold",
        "description": "Reached Limited Autonomy on at least one action type.",
    },
    "unlocked_full": {
        "label": "Full Partner", "icon": "👑", "color": "success",
        "description": "Reached Full Autonomy on at least one action type.",
    },
    "all_channels_trusted": {
        "label": "Everywhere at Once", "icon": "🌐", "color": "success",
        "description": "Reached Full Autonomy on every tracked action type.",
    },
    "clean_streak_30": {
        "label": "Clean Streak", "icon": "✨", "color": "gold",
        "description": "30 days with zero fair housing compliance flags on outbound messages.",
    },
    "comeback": {
        "label": "Comeback", "icon": "🔄", "color": "olive",
        "description": "Recovered from a rejected draft to reach Limited Autonomy or higher on that action type.",
    },
}


def get_level_for_score(score: float) -> dict:
    level = LEVELS[0]
    for l in LEVELS:
        if score >= l["min_score"]:
            level = l
    return level


def get_next_level(score: float) -> dict | None:
    for l in LEVELS:
        if l["min_score"] > score:
            return l
    return None  # already at the top level


def get_hints(trust_scores: list[TrustScore]) -> list[dict]:
    """
    One actionable hint per action type not yet at full autonomy — how
    many more unedited sends (roughly) would close the gap to the next
    threshold, computed from the real scoring deltas in trust_service.py
    rather than a made-up number.
    """
    from app.services.trust_service import SCORE_DELTAS

    hints = []
    for ts in trust_scores:
        if ts.score >= settings.TRUST_THRESHOLD_AUTONOMOUS:
            continue
        target = settings.TRUST_THRESHOLD_LIMITED if ts.score < settings.TRUST_THRESHOLD_LIMITED else settings.TRUST_THRESHOLD_AUTONOMOUS
        target_label = "Limited Autonomy" if target == settings.TRUST_THRESHOLD_LIMITED else "Full Autonomy"
        gap = target - ts.score
        actions_needed = max(1, int(-(-gap // SCORE_DELTAS["sent_unedited"])))  # ceil division
        hints.append({
            "action_type": ts.action_type.value,
            "current_score": ts.score,
            "target_level": target_label,
            "hint": f"About {actions_needed} more unedited send{'s' if actions_needed != 1 else ''} on "
                    f"{ts.action_type.value.replace('_', ' ')} would reach {target_label}. Editing drafts less "
                    f"(when they're already right) is the single fastest way to build this.",
        })
    return hints


def evaluate_and_award_badges(db: Session, user_id: str) -> list[dict]:
    """Checks all badge criteria, awards any newly-earned ones, returns the full badge list (earned + locked)."""
    trust_scores = db.query(TrustScore).filter(TrustScore.user_id == user_id).all()
    already_earned = {b.badge_key for b in db.query(TrustBadge).filter(TrustBadge.user_id == user_id).all()}
    newly_earned = []

    def award(key: str):
        if key not in already_earned:
            db.add(TrustBadge(user_id=user_id, badge_key=key))
            already_earned.add(key)
            newly_earned.append(key)

    total_actions = sum(ts.total_actions for ts in trust_scores)
    total_unedited = sum(ts.actions_sent_unedited for ts in trust_scores)

    if total_actions >= 1:
        award("first_steps")
    if total_unedited >= 10:
        award("quick_draw")
    if total_actions >= 50:
        award("prolific")
    if any(ts.automation_level.value in ("limited_autonomy", "full_autonomy") for ts in trust_scores):
        award("unlocked_limited")
    if any(ts.automation_level.value == "full_autonomy" for ts in trust_scores):
        award("unlocked_full")
    if trust_scores and all(ts.automation_level.value == "full_autonomy" for ts in trust_scores):
        award("all_channels_trusted")

    # Comeback: any action type with at least one "rejected" event followed
    # later by the score reaching Limited Autonomy or higher.
    for ts in trust_scores:
        if ts.score < settings.TRUST_THRESHOLD_LIMITED:
            continue
        had_rejection = (
            db.query(TrustEvent)
            .filter(TrustEvent.user_id == user_id, TrustEvent.action_type == ts.action_type, TrustEvent.outcome == "rejected")
            .first()
        )
        if had_rejection:
            award("comeback")

    # Clean streak: no compliance-flagged outbound messages in the last 30 days.
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_flag = (
        db.query(Message)
        .filter(Message.user_id == user_id, Message.compliance_flagged == True, Message.created_at >= cutoff)  # noqa: E712
        .first()
    )
    has_any_outbound = db.query(Message).filter(Message.user_id == user_id, Message.created_at >= cutoff).first()
    if has_any_outbound and not recent_flag:
        award("clean_streak_30")

    db.commit()

    return [
        {**BADGE_DEFINITIONS[key], "key": key, "earned": key in already_earned, "newly_earned": key in newly_earned}
        for key in BADGE_DEFINITIONS
    ]


def get_gamification_summary(db: Session, user_id: str) -> dict:
    trust_scores = db.query(TrustScore).filter(TrustScore.user_id == user_id).all()
    overall_score = round(sum(ts.score for ts in trust_scores) / len(trust_scores), 1) if trust_scores else 0.0

    badges = evaluate_and_award_badges(db, user_id)
    level = get_level_for_score(overall_score)
    next_level = get_next_level(overall_score)

    return {
        "overall_score": overall_score,
        "level": level,
        "next_level": next_level,
        "points_to_next_level": round(next_level["min_score"] - overall_score, 1) if next_level else 0,
        "badges": badges,
        "badges_earned_count": len([b for b in badges if b["earned"]]),
        "hints": get_hints(trust_scores),
        "per_action_scores": [
            {
                "action_type": ts.action_type.value,
                "score": ts.score,
                "automation_level": ts.automation_level.value,
                "total_actions": ts.total_actions,
                "actions_sent_unedited": ts.actions_sent_unedited,
                "actions_edited": ts.actions_edited,
                "actions_rejected": ts.actions_rejected,
                "level": get_level_for_score(ts.score),
            }
            for ts in trust_scores
        ],
    }
