from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PropertyBase(BaseModel):
    address: str
    city: str
    state: str
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    price: Optional[float] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    property_type: Optional[str] = None
    year_built: Optional[int] = None
    status: str = "active"
    days_on_market: Optional[int] = None
    description: Optional[str] = None


class PropertyCreate(PropertyBase):
    source: str = "manual"
    source_listing_id: Optional[str] = None
    source_url: Optional[str] = None


class PropertyUpdate(BaseModel):
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    price: Optional[float] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    property_type: Optional[str] = None
    year_built: Optional[int] = None
    status: Optional[str] = None
    days_on_market: Optional[int] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    photos: Optional[list] = None
    mls_number: Optional[str] = None
    lot_size_sqft: Optional[int] = None
    garage_spaces: Optional[int] = None
    listing_agent_name: Optional[str] = None
    listing_agent_email: Optional[str] = None
    listing_agent_phone: Optional[str] = None
    listing_brokerage: Optional[str] = None


class PropertyOut(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    thumbnail_url: Optional[str] = None
    photos: Optional[list] = None
    mls_number: Optional[str] = None
    lot_size_sqft: Optional[int] = None
    garage_spaces: Optional[int] = None
    listing_agent_name: Optional[str] = None
    listing_agent_email: Optional[str] = None
    listing_agent_phone: Optional[str] = None
    listing_brokerage: Optional[str] = None
    compliance_risk: Optional[str] = None
    compliance_flags: Optional[list] = None
    created_at: datetime
    updated_at: datetime


class ComparableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comp_property_id: UUID
    similarity_score: float
    price_per_sqft_delta: Optional[float] = None
    adjusted_value_estimate: Optional[float] = None
