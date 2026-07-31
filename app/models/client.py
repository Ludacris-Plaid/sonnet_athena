import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

# Pipeline stages, in order. Kept as a plain list (not a DB enum) so the
# board can be reordered/relabeled without a migration — validated in
# client_service.py instead.
PIPELINE_STAGES = [
    "lead", "contacted", "qualified", "showing",
    "offer", "under_contract", "closed_won", "closed_lost",
]
LEAD_TEMPERATURES = ["hot", "warm", "cold"]


class Client(Base):
    """A realtor's client (buyer/seller) — the CRM's core record."""
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    owning_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    client_type = Column(String, default="buyer")  # buyer | seller | both
    status = Column(String, default="active")  # active | inactive
    budget_max = Column(Float, nullable=True)
    preferred_city = Column(String, nullable=True)
    pre_approved = Column(Boolean, default=False)
    timeline = Column(String, nullable=True)  # e.g. "1-3mo", "immediate"

    # --- CRM fields ---
    pipeline_stage = Column(String, default="lead")  # see PIPELINE_STAGES above
    lead_temperature = Column(String, default="warm")  # hot | warm | cold — see LEAD_TEMPERATURES
    lead_source = Column(String, nullable=True)  # e.g. "referral", "zillow", "open house", "website"
    tags = Column(JSON, default=list)  # list[str], free-form
    custom_fields = Column(JSON, default=dict)  # dict[str, str], for anything not modeled explicitly
    deal_value = Column(Float, nullable=True)  # estimated $ value of this deal, for pipeline reporting

    # Relationship linking (household/referral graph) — self-referential.
    referred_by_client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    household_name = Column(String, nullable=True)  # e.g. "The Smith Family" — groups related contacts loosely

    # Contact preferences / compliance
    do_not_contact = Column(Boolean, default=False)
    email_opt_in = Column(Boolean, default=True)
    sms_opt_in = Column(Boolean, default=True)

    # Engagement tracking — last_contacted_at is updated whenever a Message
    # links to this client (see client_service.py); next_follow_up_at is
    # set manually or by a ClientTask due date. Powers the lead-scoring
    # service and stale-lead alerts.
    last_contacted_at = Column(DateTime, nullable=True)
    next_follow_up_at = Column(DateTime, nullable=True)
    engagement_score = Column(Float, nullable=True)  # 0-100, recomputed by lead_scoring_service

    # External CRM linkage — set when this client came from, or was pushed
    # to, a connected CRM. Used to match records on repeat syncs instead of
    # creating duplicates. Nullable: clients created directly in RealtyAI
    # have no external counterpart until explicitly pushed.
    external_provider = Column(String, nullable=True)  # "followupboss" | "hubspot" | "csv" | null
    external_id = Column(String, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ClientNote(Base):
    """Manually-logged notes — distinct from Message (actual communications)."""
    __tablename__ = "client_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    body = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ClientActivityLog(Base):
    """
    System-generated timeline events that aren't a message or a manual
    note — stage changes, tag changes, merges. Combined with Message and
    ClientNote at query time to build the full activity timeline (see
    client_timeline_service.py) rather than duplicating data into one
    mega-table.
    """
    __tablename__ = "client_activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    event_type = Column(String, nullable=False)  # "stage_change" | "tag_added" | "merged" | "created"
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ClientTask(Base):
    """Reminders/follow-ups tied to a client."""
    __tablename__ = "client_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)
    due_at = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SavedSearch(Base):
    """Property search criteria saved per client, matched against new listings."""
    __tablename__ = "saved_searches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)

    name = Column(String, nullable=False)  # e.g. "3bd Edmonton under 500k"
    city = Column(String, nullable=True)
    min_beds = Column(Integer, nullable=True)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    property_type = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
