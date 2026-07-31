from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PropertyAnalysisRequest(BaseModel):
    property_id: UUID
    include_comps: bool = True
    max_comps: int = 5


class PropertyAnalysisResponse(BaseModel):
    property_id: UUID
    estimated_value: Optional[float] = None
    value_range_low: Optional[float] = None
    value_range_high: Optional[float] = None
    comps_used: int
    ai_summary: str
    investment_notes: Optional[str] = None


class InboxDraftRequest(BaseModel):
    message_id: UUID
    tones: list[str] = ["professional", "warm", "brief", "urgent"]
