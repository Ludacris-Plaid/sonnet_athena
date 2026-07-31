import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Property(Base):
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    address = Column(String, nullable=False)
    city = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False)
    postal_code = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    price = Column(Float, nullable=True)
    beds = Column(Integer, nullable=True)
    baths = Column(Float, nullable=True)
    sqft = Column(Integer, nullable=True)
    property_type = Column(String, nullable=True)  # single_family, condo, multi_family...
    year_built = Column(Integer, nullable=True)

    status = Column(String, default="active")  # active, pending, sold, off_market
    days_on_market = Column(Integer, nullable=True)
    description = Column(String, nullable=True)

    # Photos — thumbnail_url is the card image; photos is the full gallery
    # shown in the detail modal. Both nullable since not every source
    # provides images (e.g. a bare CSV import might not).
    thumbnail_url = Column(String, nullable=True)
    photos = Column(JSON, nullable=True)  # list[str] of image URLs

    # Additional specs shown in the detail modal
    mls_number = Column(String, nullable=True)
    lot_size_sqft = Column(Integer, nullable=True)
    garage_spaces = Column(Integer, nullable=True)

    # Listing agent — who's actually selling it, for the "quick
    # communication" feature in the detail modal. Not a RealtyAI user or
    # CRM Client — an external contact tied to this specific listing.
    listing_agent_name = Column(String, nullable=True)
    listing_agent_email = Column(String, nullable=True)
    listing_agent_phone = Column(String, nullable=True)
    listing_brokerage = Column(String, nullable=True)

    source = Column(String, default="demo")  # "demo" | "reso" | "bridge" | "attom" | "csv" | "manual"
    source_listing_id = Column(String, nullable=True)
    source_url = Column(String, nullable=True)

    raw_data = Column(JSON, nullable=True)  # full normalized payload from the source

    # Fast keyword-only fair housing scan, run automatically on every
    # ingest/save (see property_service.py). "caution"/"high"/"low"/null.
    # This is the cheap first pass only — no LLM call at ingest time, so
    # bulk ingestion of many listings stays fast. Run a full LLM-backed
    # review on demand via POST /properties/{id}/compliance-check.
    compliance_risk = Column(String, nullable=True)
    compliance_flags = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    neighborhood_id = Column(UUID(as_uuid=True), ForeignKey("neighborhoods.id"), nullable=True)
    neighborhood = relationship("Neighborhood", back_populates="properties")
