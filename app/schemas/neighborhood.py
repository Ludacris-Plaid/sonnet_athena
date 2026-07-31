from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NeighborhoodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: str
    state: str
    median_price: Optional[float] = None
    price_trend_90d_pct: Optional[float] = None
    avg_days_on_market: Optional[int] = None
    inventory_count: Optional[int] = None
    turnover_rate_pct: Optional[float] = None
    opportunity_score: Optional[float] = None


class NeighborhoodCompareRequest(BaseModel):
    city: str
    state: str
    neighborhood_names: list[str]
