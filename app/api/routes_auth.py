"""
With Supabase Auth, signup and login happen entirely client-side via
supabase-js (see frontend/shared/supabase-client.js) — this backend never
sees a password.

What's left here:
  - POST /auth/complete-signup — called once, right after a Supabase auth
    account is created, to redeem an invite code and create the
    Organization + User(profile) row. Requires a valid Supabase bearer
    token (the user must already exist in Supabase Auth).
  - POST /auth/admin/invite-codes — unchanged, platform-admin only.
"""
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.supabase_auth import verify_supabase_token
from app.core.security import generate_invite_code
from app.models.org import Organization, User, InviteCode, PlanTier
from app.api.deps import require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class CompleteSignupRequest(BaseModel):
    invite_code: str
    org_name: str
    full_name: str


class CompleteSignupResponse(BaseModel):
    org_id: str
    user_id: str
    plan_tier: PlanTier


class InviteCodeCreateRequest(BaseModel):
    plan_tier: PlanTier = PlanTier.LIGHT
    created_by_admin_email: str | None = None


class InviteCodeOut(BaseModel):
    code: str
    plan_tier: PlanTier


@router.post("/complete-signup", response_model=CompleteSignupResponse)
def complete_signup(
    payload: CompleteSignupRequest,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token — sign up with Supabase first")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verify_supabase_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired Supabase token")

    supabase_user_id = claims.get("sub")
    email = claims.get("email")
    if not supabase_user_id or not email:
        raise HTTPException(status_code=401, detail="Token missing required claims")

    if db.query(User).filter(User.id == supabase_user_id).first():
        raise HTTPException(status_code=400, detail="This account has already completed signup")

    invite = db.query(InviteCode).filter(InviteCode.code == payload.invite_code).first()
    if not invite or invite.is_redeemed:
        raise HTTPException(status_code=400, detail="Invalid or already-used invite code")
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite code has expired")

    org = Organization(name=payload.org_name, plan_tier=invite.plan_tier)
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        id=supabase_user_id,  # same UUID as Supabase auth.users.id — not generated here
        org_id=org.id,
        email=email,
        full_name=payload.full_name,
    )
    db.add(user)

    invite.is_redeemed = True
    invite.redeemed_by_org_id = org.id
    invite.redeemed_at = datetime.now(timezone.utc)
    db.add(invite)

    db.commit()

    return CompleteSignupResponse(org_id=str(org.id), user_id=str(user.id), plan_tier=org.plan_tier)


@router.post("/admin/invite-codes", response_model=InviteCodeOut, dependencies=[Depends(require_admin)])
def create_invite_code(payload: InviteCodeCreateRequest, db: Session = Depends(get_db)):
    code = InviteCode(
        code=generate_invite_code(),
        plan_tier=payload.plan_tier,
        created_by_admin_email=payload.created_by_admin_email,
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return InviteCodeOut(code=code.code, plan_tier=code.plan_tier)
