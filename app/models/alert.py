import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class AlertRuleType(str, PyEnum):
    PRICE_DROP_PCT = "price_drop_pct"        # fires when a property's price drops >= threshold %
    NEW_LISTING_MATCH = "new_listing_match"  # fires when a newly ingested listing matches a client's criteria
    LONG_DOM = "long_dom"                    # fires when a listing exceeds a days-on-market threshold
    COMPLIANCE_FLAG = "compliance_flag"      # system rule: fires whenever any outbound message is compliance-flagged
    STALE_LEAD = "stale_lead"                # fires when a client hasn't been contacted in N days


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)  # for NEW_LISTING_MATCH

    rule_type = Column(Enum(AlertRuleType), nullable=False)
    params = Column(JSON, nullable=True)  # e.g. {"threshold_pct": 5} or {"dom_days": 60}
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # true for auto-provisioned rules like COMPLIANCE_FLAG, not user-created

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("alert_rules.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)  # for COMPLIANCE_FLAG events
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)  # for STALE_LEAD / NEW_LISTING_MATCH events

    headline = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    severity = Column(String, default="info")  # "info" | "warning" | "critical" — compliance flags use warning/critical

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
