"""
Platform admin operations: user CRUD (suspend/reinstate/ban), org
management, and financial/usage statistics. Every mutating function here
writes to AdminAuditLog — this is deliberate and non-optional, called from
both the admin UI routes AND the admin agent's tool dispatch, so there is
exactly one code path for "an admin changed something" and it always logs.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.org import User, Organization, PlanTier
from app.models.admin_audit import AdminAuditLog
from app.models.message import Message

# Reference pricing for MRR estimation — adjust to your actual Stripe prices.
PLAN_PRICING_USD = {
    PlanTier.LIGHT: 100,
    PlanTier.MEDIUM: 250,
    PlanTier.HEAVY: 500,
}

# Rough DeepSeek cost estimate for margin visibility — this is a
# configurable placeholder, not a live rate. Update to match your actual
# negotiated/current DeepSeek pricing per 1M tokens (blended input+output).
DEEPSEEK_COST_PER_1M_TOKENS_USD = 0.55


def log_admin_action(
    db: Session,
    admin_user_id: str,
    admin_email: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    source: str = "ui",
    detail: dict | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        admin_email=admin_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        source=source,
        detail=detail,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def list_all_users(db: Session, search: str | None = None, status: str | None = None) -> list[User]:
    query = db.query(User)
    if search:
        like = f"%{search}%"
        query = query.filter((User.full_name.ilike(like)) | (User.email.ilike(like)))
    if status:
        query = query.filter(User.status == status)
    return query.order_by(User.created_at.desc()).all()


def get_user(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def update_user_status(
    db: Session,
    admin: User,
    user_id: str,
    new_status: str,
    reason: str | None = None,
    source: str = "ui",
) -> User:
    """new_status: 'active' | 'suspended' | 'banned'"""
    if new_status not in ("active", "suspended", "banned"):
        raise ValueError(f"Invalid status: {new_status}")

    user = get_user(db, user_id)
    if not user:
        raise ValueError("User not found")
    if user.id == admin.id and new_status != "active":
        raise ValueError("You can't suspend or ban your own account.")

    old_status = user.status
    user.status = new_status
    user.is_active = new_status == "active"  # keep the actual auth gate in sync
    user.status_reason = reason
    user.status_changed_at = datetime.now(timezone.utc)
    user.status_changed_by = admin.id
    db.add(user)
    db.commit()
    db.refresh(user)

    log_admin_action(
        db, str(admin.id), admin.email,
        action=f"user_status_{new_status}",
        target_type="user", target_id=str(user.id),
        source=source,
        detail={"old_status": old_status, "new_status": new_status, "reason": reason},
    )
    return user


def update_user_profile(db: Session, admin: User, user_id: str, full_name: str | None, is_admin: bool | None, source: str = "ui") -> User:
    user = get_user(db, user_id)
    if not user:
        raise ValueError("User not found")

    before = {"full_name": user.full_name, "is_admin": user.is_admin}
    if full_name is not None:
        user.full_name = full_name
    if is_admin is not None:
        if user.id == admin.id and not is_admin:
            raise ValueError("You can't remove your own admin access.")
        user.is_admin = is_admin
    db.add(user)
    db.commit()
    db.refresh(user)

    log_admin_action(
        db, str(admin.id), admin.email,
        action="user_profile_update",
        target_type="user", target_id=str(user.id),
        source=source,
        detail={"before": before, "after": {"full_name": user.full_name, "is_admin": user.is_admin}},
    )
    return user


# ---------------------------------------------------------------------------
# Organization actions (wrapping what routes_admin.py already partially had,
# now with audit logging)
# ---------------------------------------------------------------------------

def adjust_plan_tier(db: Session, admin: User, org_id: str, new_tier: str, source: str = "ui") -> Organization:
    if new_tier not in (t.value for t in PlanTier):
        raise ValueError(f"Invalid plan tier: {new_tier}")
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("Organization not found")

    old_tier = org.plan_tier.value
    org.plan_tier = new_tier
    db.add(org)
    db.commit()
    db.refresh(org)

    log_admin_action(
        db, str(admin.id), admin.email,
        action="adjust_plan_tier",
        target_type="organization", target_id=str(org.id),
        source=source,
        detail={"old_tier": old_tier, "new_tier": new_tier},
    )
    return org


def set_org_active(db: Session, admin: User, org_id: str, is_active: bool, source: str = "ui") -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("Organization not found")
    org.is_active = is_active
    db.add(org)
    db.commit()
    db.refresh(org)

    log_admin_action(
        db, str(admin.id), admin.email,
        action="org_activate" if is_active else "org_deactivate",
        target_type="organization", target_id=str(org.id),
        source=source,
    )
    return org


# ---------------------------------------------------------------------------
# Financial / usage statistics
# ---------------------------------------------------------------------------

def get_platform_overview(db: Session) -> dict:
    orgs = db.query(Organization).all()
    users = db.query(User).all()

    mrr = sum(PLAN_PRICING_USD.get(o.plan_tier, 0) for o in orgs if o.is_active)
    total_tokens_used = sum(o.tokens_used_this_period for o in orgs)
    estimated_token_cost = round(total_tokens_used / 1_000_000 * DEEPSEEK_COST_PER_1M_TOKENS_USD, 2)
    estimated_gross_margin = round(mrr - estimated_token_cost, 2)

    tier_breakdown = {}
    for tier in PlanTier:
        count = len([o for o in orgs if o.plan_tier == tier and o.is_active])
        tier_breakdown[tier.value] = {"org_count": count, "mrr": count * PLAN_PRICING_USD[tier]}

    status_breakdown = {}
    for s in ("active", "suspended", "banned"):
        status_breakdown[s] = len([u for u in users if u.status == s])

    return {
        "total_organizations": len(orgs),
        "active_organizations": len([o for o in orgs if o.is_active]),
        "total_users": len(users),
        "user_status_breakdown": status_breakdown,
        "estimated_mrr_usd": mrr,
        "total_tokens_used_this_period": total_tokens_used,
        "estimated_token_cost_usd": estimated_token_cost,
        "estimated_gross_margin_usd": estimated_gross_margin,
        "plan_tier_breakdown": tier_breakdown,
    }


def get_signup_trend(db: Session, days: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(func.date(User.created_at).label("day"), func.count(User.id).label("count"))
        .filter(User.created_at >= cutoff)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    return [{"date": str(r.day), "count": r.count} for r in rows]


def get_message_volume_trend(db: Session, days: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(func.date(Message.created_at).label("day"), func.count(Message.id).label("count"))
        .filter(Message.created_at >= cutoff)
        .group_by(func.date(Message.created_at))
        .order_by(func.date(Message.created_at))
        .all()
    )
    return [{"date": str(r.day), "count": r.count} for r in rows]
