import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Comparable(Base):
    """
    Links a subject property to a comp property, with the computed
    similarity/adjustment data used to justify a CMA price.
    """
    __tablename__ = "comparables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    subject_property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    comp_property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)

    similarity_score = Column(Float, nullable=False)  # 0-1, from embedding cosine similarity
    price_per_sqft_delta = Column(Float, nullable=True)
    adjusted_value_estimate = Column(Float, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
