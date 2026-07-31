"""
Platform admin dashboard endpoints: org overview, usage/margin, invite
codes, full user CRUD, financial/usage statistics, audit log, and the
admin agent chat. Every mutating endpoint here logs to AdminAuditLog via
admin_service.py — see that module's docstring.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import require_admin, get_current_user
from app.models.org import Organization, InviteCode, User
from app.models.admin_audit import AdminAuditLog
from app.schemas.admin import (
    UserOut, UpdateUserStatusRequest, UpdateUserProfileRequest,
    AdjustPlanTierRequest, AuditLogOut, AdminChatRequest, AdminChatResponse,
)
from app.services import admin_service
from app.services import conversation_service
from app.services import settings_service
from app.services.admin_agent_service import run_admin_chat

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me", dependencies=[Depends(require_admin)])
def admin_me(admin: User = Depends(get_current_user)):
    """Lets the admin frontend confirm admin status right after login."""
    return {"id": str(admin.id), "email": admin.email, "full_name": admin.full_name, "is_admin": admin.is_admin}


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

@router.get("/organizations", dependencies=[Depends(require_admin)])
def list_organizations(db: Session = Depends(get_db)):
    orgs = db.query(Organization).all()
    return [
        {
            "id": o.id,
            "name": o.name,
            "plan_tier": o.plan_tier,
            "monthly_token_allowance": o.monthly_token_allowance,
            "tokens_used_this_period": o.tokens_used_this_period,
            "utilization_pct": round(100 * o.tokens_used_this_period / o.monthly_token_allowance, 1)
            if o.monthly_token_allowance
            else None,
            "is_active": o.is_active,
        }
        for o in orgs
    ]


@router.post("/organizations/{org_id}/deactivate")
def deactivate_org(org_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        admin_service.set_org_active(db, admin, org_id, False)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/organizations/{org_id}/activate")
def activate_org(org_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        admin_service.set_org_active(db, admin, org_id, True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/organizations/{org_id}/plan-tier")
def change_plan_tier(org_id: str, payload: AdjustPlanTierRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        org = admin_service.adjust_plan_tier(db, admin, org_id, payload.new_tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "new_tier": org.plan_tier.value}


@router.get("/invite-codes", dependencies=[Depends(require_admin)])
def list_invite_codes(db: Session = Depends(get_db)):
    return db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Users — full CRUD
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
def list_users(search: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    return admin_service.list_all_users(db, search=search, status=status)


@router.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = admin_service.get_user(db, str(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UpdateUserProfileRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return admin_service.update_user_profile(db, admin, str(user_id), payload.full_name, payload.is_admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{user_id}/status", response_model=UserOut)
def set_user_status(user_id: UUID, payload: UpdateUserStatusRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """status: 'active' (reinstate) | 'suspended' | 'banned' ('boot')"""
    try:
        return admin_service.update_user_status(db, admin, str(user_id), payload.status, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Financial / usage statistics
# ---------------------------------------------------------------------------

@router.get("/stats/overview", dependencies=[Depends(require_admin)])
def stats_overview(db: Session = Depends(get_db)):
    return admin_service.get_platform_overview(db)


@router.get("/stats/signups", dependencies=[Depends(require_admin)])
def stats_signups(days: int = 30, db: Session = Depends(get_db)):
    return admin_service.get_signup_trend(db, days)


@router.get("/stats/message-volume", dependencies=[Depends(require_admin)])
def stats_message_volume(days: int = 30, db: Session = Depends(get_db)):
    return admin_service.get_message_volume_trend(db, days)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit-log", response_model=list[AuditLogOut], dependencies=[Depends(require_admin)])
def get_audit_log(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Admin's own Athena — "god mode with guardrails"
# ---------------------------------------------------------------------------

@router.post("/agent/chat", response_model=AdminChatResponse)
def admin_agent_chat(payload: AdminChatRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    conv = conversation_service.get_or_create_active_conversation(db, str(admin.org_id), str(admin.id), context="admin_agent")
    result = run_admin_chat(db, admin, str(conv.id), payload.message)
    return AdminChatResponse(reply=result["reply"], conversation_id=str(conv.id))


# ---------------------------------------------------------------------------
# Platform-wide settings (infrastructure keys — DeepSeek, Supabase, OAuth
# app credentials, Twilio, Hermes). Admin-only because these are shared
# across every org; a mistaken edit here affects the whole platform.
# ---------------------------------------------------------------------------

@router.get("/settings/keys", dependencies=[Depends(require_admin)])
def list_platform_keys(db: Session = Depends(get_db)):
    return settings_service.list_settings_for_scope(db, None, "platform")


@router.post("/settings/keys")
def set_platform_key(payload: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        settings_service.set_setting(db, None, payload["key"], payload["value"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    admin_service.log_admin_action(db, str(admin.id), admin.email, action="set_platform_setting", target_type="setting", target_id=payload["key"])
    return {"ok": True}


@router.delete("/settings/keys/{key}")
def delete_platform_key(key: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings_service.delete_setting(db, None, key)
    admin_service.log_admin_action(db, str(admin.id), admin.email, action="delete_platform_setting", target_type="setting", target_id=key)
    return {"ok": True}
