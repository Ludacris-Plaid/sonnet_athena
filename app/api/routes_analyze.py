from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.schemas.analysis import PropertyAnalysisRequest, PropertyAnalysisResponse
from app.services.analysis_service import analyze_property, investment_analysis

router = APIRouter(prefix="/analyze", tags=["analysis"])


@router.post("/property", response_model=PropertyAnalysisResponse)
def analyze(payload: PropertyAnalysisRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        result = analyze_property(db, payload.property_id, max_comps=payload.max_comps)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.post("/investment/{property_id}")
def investment(property_id: str, assumptions: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return investment_analysis(db, property_id, assumptions)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
