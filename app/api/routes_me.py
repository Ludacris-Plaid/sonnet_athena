"""
Self-service endpoints for the current user's own account — distinct from
routes_admin.py's user management (which operates on any user, admin-only).
Currently just onboarding status; a natural place for future personal
preferences.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/onboarding-status")
def onboarding_status(user: User = Depends(get_current_user)):
    return {"has_completed_onboarding": user.has_completed_onboarding}


@router.post("/complete-onboarding")
def complete_onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.has_completed_onboarding = True
    db.add(user)
    db.commit()
    return {"ok": True}


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)):
    from app.prompts.athena_persona import RESPONSE_STYLE_LABELS
    return {
        "full_name": user.full_name,
        "email": user.email,
        "response_style": user.response_style,
        "response_style_options": RESPONSE_STYLE_LABELS,
    }


@router.post("/preferences")
def set_preferences(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.prompts.athena_persona import RESPONSE_STYLE_LABELS
    style = payload.get("response_style")
    if style is not None:
        if style not in RESPONSE_STYLE_LABELS:
            raise HTTPException(status_code=400, detail=f"Invalid response_style. Choose one of: {list(RESPONSE_STYLE_LABELS)}")
        user.response_style = style
    db.add(user)
    db.commit()
    return {"ok": True}
