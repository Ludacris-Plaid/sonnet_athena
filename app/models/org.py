"""
Multi-tenant organization, users, invite codes, and subscription plan.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class PlanTier(str, PyEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    plan_tier = Column(Enum(PlanTier), default=PlanTier.LIGHT, nullable=False)

    # Billing / usage metering
    monthly_token_allowance = Column(Integer, default=200_000)  # DeepSeek tokens included in plan
    tokens_used_this_period = Column(Integer, default=0)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Business profile — org-level (one brokerage identity shared by
    # everyone in the org), pulled automatically into content generation,
    # document drafts, and outbound agent-to-agent messages so nobody has
    # to retype their name/license/contact info every time.
    brokerage_name = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    license_number = Column(String, nullable=True)  # US state license # or Canadian provincial registration #
    license_jurisdiction = Column(String, nullable=True)  # e.g. "TX" or "Ontario (RECO)"
    business_phone = Column(String, nullable=True)
    business_email = Column(String, nullable=True)
    business_address = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)

    users = relationship("User", back_populates="org")


class User(Base):
    """
    Profile row for a Supabase-authenticated user. `id` is NOT generated
    here — it's the same UUID as the corresponding Supabase `auth.users.id`,
    set explicitly when the row is created in routes_auth.complete_signup.
    No password is stored here; Supabase Auth owns credentials entirely.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True)  # = Supabase auth.users.id, not auto-generated
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)  # platform-level admin (you), not org admin
    is_active = Column(Boolean, default=True)  # kept as the actual auth gate (see deps.py) — status below is kept in sync with this

    # Richer status than the plain is_active boolean, for admin CRUD:
    # "active" | "suspended" (temporary, reversible) | "banned" (for cause).
    # is_active is always kept in sync (False whenever status != "active")
    # so deps.py's existing auth check doesn't need to change.
    status = Column(String, default="active", nullable=False)
    status_reason = Column(String, nullable=True)
    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by = Column(UUID(as_uuid=True), nullable=True)  # admin user id who made the change

    # Onboarding tour — tracked server-side (not localStorage) for the same
    # reason conversations persist server-side: it shouldn't reset just
    # because someone clears browser storage or logs in from a new device.
    has_completed_onboarding = Column(Boolean, default=False)

    # Small, explicit personality controls — NOT a free-text prompt
    # override. The core character (warm, direct, strategic) doesn't
    # change; this only adjusts response length, since that's mostly a
    # token-cost/preference question, not a character one.
    response_style = Column(String, default="verbose")  # "verbose" | "balanced" | "concise"

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    org = relationship("Organization", back_populates="users")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, unique=True, nullable=False, index=True)
    plan_tier = Column(Enum(PlanTier), default=PlanTier.LIGHT, nullable=False)

    is_redeemed = Column(Boolean, default=False)
    redeemed_by_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    redeemed_at = Column(DateTime, nullable=True)

    created_by_admin_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
