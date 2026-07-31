"""
Org-level runtime settings (regular Settings page). Platform-wide settings
(admin-only) are exposed separately — see routes_admin.py's /admin/settings
endpoints, same underlying settings_service, different scope enforced.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.settings import SetSettingRequest
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/keys")
def list_keys(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return settings_service.list_settings_for_scope(db, str(user.org_id), "org")


@router.post("/keys")
def set_key(payload: SetSettingRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        settings_service.set_setting(db, str(user.org_id), payload.key, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/keys/{key}")
def delete_key(key: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings_service.delete_setting(db, str(user.org_id), key)
    return {"ok": True}


@router.get("/telephony-status")
def telephony_status(user: User = Depends(get_current_user)):
    """
    Whether Twilio SMS/voice is configured — a plain boolean any user can
    see, not the actual secret values (those are platform-admin-only,
    same reasoning as everything else in the "platform" scope).
    """
    from app.core.config import settings as env_settings
    configured = bool(env_settings.TWILIO_ACCOUNT_SID and env_settings.TWILIO_AUTH_TOKEN and env_settings.TWILIO_PHONE_NUMBER)
    return {"configured": configured, "phone_number": env_settings.TWILIO_PHONE_NUMBER if configured else None}


@router.get("/business-profile")
def get_business_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.org import Organization
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    return {
        "brokerage_name": org.brokerage_name,
        "agent_name": org.agent_name,
        "license_number": org.license_number,
        "license_jurisdiction": org.license_jurisdiction,
        "business_phone": org.business_phone,
        "business_email": org.business_email,
        "business_address": org.business_address,
        "logo_url": org.logo_url,
    }


@router.post("/business-profile")
def set_business_profile(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.org import Organization
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    fields = ["brokerage_name", "agent_name", "license_number", "license_jurisdiction", "business_phone", "business_email", "business_address", "logo_url"]
    for f in fields:
        if f in payload:
            setattr(org, f, payload[f] or None)
    db.add(org)
    db.commit()
    return {"ok": True}
