import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, nullable=False)
    city = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False)

    median_price = Column(Float, nullable=True)
    price_trend_90d_pct = Column(Float, nullable=True)  # % change over last 90 days
    avg_days_on_market = Column(Integer, nullable=True)
    inventory_count = Column(Integer, nullable=True)
    turnover_rate_pct = Column(Float, nullable=True)  # % of homes that sold in last 12mo

    # Composite score computed by analysis_service, 0-100
    opportunity_score = Column(Float, nullable=True)

    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    properties = relationship("Property", back_populates="neighborhood")
