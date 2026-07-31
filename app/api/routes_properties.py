from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.property import Property
from app.models.price_history import PriceHistory
from app.models.comparable import Comparable
from app.models.alert import AlertEvent
from app.schemas.property import PropertyOut, ComparableOut, PropertyCreate, PropertyUpdate
from app.services.property_service import ingest_listings, find_comps
from app.services.alert_service import evaluate_alerts_for_batch
from app.services.compliance_service import screen_listing_text
from app.services.property_csv_service import import_csv
from app.services.agent_outreach_service import draft_message_to_agent, send_message_to_agent, PURPOSE_PRESETS
from app.scrapers.factory import list_available_sources

router = APIRouter(prefix="/properties", tags=["properties"])


class IngestRequest(BaseModel):
    city: str
    state: str
    limit: int = 50
    source: str | None = None  # "demo" | "reso" | "bridge" | "attom" — falls back to LISTINGS_SOURCE if omitted


class DraftAgentMessageRequest(BaseModel):
    purpose: str = "request_showing"  # matches PURPOSE_PRESETS, or free text
    extra_context: str | None = None


class SendAgentMessageRequest(BaseModel):
    body: str


@router.get("/sources")
def get_sources(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every listings data source option, with real configured/not-configured status — lets the user pick where to import from."""
    return list_available_sources(db, str(user.org_id))


@router.post("/ingest", response_model=list[PropertyOut])
def ingest(payload: IngestRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        properties = ingest_listings(
            db, org_id=str(user.org_id), city=payload.city, state=payload.state,
            limit=payload.limit, source_key=payload.source,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    # Fire any price-drop / long-DOM / new-listing-match alert rules against this fresh batch.
    evaluate_alerts_for_batch(db, str(user.org_id), properties)
    return properties


@router.post("/import-csv")
async def import_csv_route(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload")
    return import_csv(db, str(user.org_id), file_bytes)


@router.post("", response_model=PropertyOut)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manual single-property entry — the fourth way properties get into the system, alongside imports/CSV."""
    prop = Property(org_id=user.org_id, **payload.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("", response_model=list[PropertyOut])
def list_properties(city: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Property).filter(Property.org_id == user.org_id)
    if city:
        query = query.filter(Property.city == city)
    return query.order_by(Property.created_at.desc()).limit(200).all()


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.patch("/{property_id}", response_model=PropertyOut)
def update_property(property_id: UUID, payload: PropertyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, key, value)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/{property_id}")
def delete_property(property_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # None of these FKs cascade-delete — clean them up explicitly first, or
    # this fails with a foreign key violation the moment a property has any
    # price history (which every ingested listing does) or shows up as a
    # comp for another property.
    db.query(PriceHistory).filter(PriceHistory.property_id == property_id).delete()
    db.query(Comparable).filter(
        (Comparable.subject_property_id == property_id) | (Comparable.comp_property_id == property_id)
    ).delete()
    db.query(AlertEvent).filter(AlertEvent.property_id == property_id).delete()

    db.delete(prop)
    db.commit()
    return {"ok": True}


@router.get("/{property_id}/comps", response_model=list[ComparableOut])
def get_comps(property_id: UUID, max_comps: int = 5, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    comps = find_comps(db, prop, max_comps=max_comps)
    return [
        ComparableOut(
            comp_property_id=c["id"],
            similarity_score=c["similarity_score"],
            price_per_sqft_delta=c.get("price_per_sqft_delta"),
            adjusted_value_estimate=None,
        )
        for c in comps
    ]


@router.post("/{property_id}/compliance-check")
def deep_compliance_check(property_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Full two-pass (keyword + LLM contextual) fair housing review, on demand.
    The fast keyword-only pass already ran automatically at ingest time
    (see property_service.ingest_listings) and is reflected in
    compliance_risk/compliance_flags on the property itself — use this
    endpoint when an agent wants the deeper, LLM-reviewed check before
    publishing or sharing a listing description externally.
    """
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if not prop.description:
        return {"overall_risk": "low", "flags": [], "note": "No description text to screen."}
    return screen_listing_text(prop.description)


@router.post("/{property_id}/draft-agent-message")
def draft_agent_message(property_id: UUID, payload: DraftAgentMessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    try:
        return draft_message_to_agent(db, str(property_id), payload.purpose, payload.extra_context)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{property_id}/send-agent-message")
def send_agent_message(property_id: UUID, payload: SendAgentMessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    try:
        msg = send_message_to_agent(db, str(user.org_id), str(user.id), str(property_id), payload.body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "message_id": str(msg.id)}
