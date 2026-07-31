from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.org import User
from app.services.compliance_service import screen_listing_text, get_disclosure_reference, get_aml_overview

router = APIRouter(prefix="/compliance", tags=["compliance"])


class ScreenRequest(BaseModel):
    text: str


@router.post("/screen-listing")
def screen_listing(payload: ScreenRequest, user: User = Depends(get_current_user)):
    return screen_listing_text(payload.text)


@router.get("/disclosure-reference/{jurisdiction}")
def disclosure_reference(jurisdiction: str, user: User = Depends(get_current_user)):
    """jurisdiction examples: US-CA, US-TX, US-NY, US-FL, CA-ON, CA-BC, CA-AB, US-generic"""
    return get_disclosure_reference(jurisdiction)


@router.get("/aml-overview/{country}")
def aml_overview(country: str, user: User = Depends(get_current_user)):
    """country: US or CA"""
    return get_aml_overview(country)
