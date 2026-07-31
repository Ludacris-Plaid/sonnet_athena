import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class DocumentType(str, PyEnum):
    MARKETING_FLYER = "marketing_flyer"
    LISTING_DESCRIPTION = "listing_description"
    DISCLOSURE_DRAFT = "disclosure_draft"  # explicitly a non-binding starting draft — see document_prompts.py
    BUYER_GUIDE = "buyer_guide"
    SELLER_GUIDE = "seller_guide"
    EMAIL_NEWSLETTER = "email_newsletter"
    TRANSACTION_CHECKLIST = "transaction_checklist"
    COVER_LETTER = "cover_letter"
    LISTING_AGREEMENT_PREP = "listing_agreement_prep"  # deal-points summary, NOT the binding listing agreement itself
    PURCHASE_OFFER_PREP = "purchase_offer_prep"        # deal-points summary, NOT the binding purchase agreement itself
    UPLOADED_OTHER = "uploaded_other"  # for imported documents that don't fit a generated category


class DocumentSource(str, PyEnum):
    UPLOADED = "uploaded"
    GENERATED = "generated"


class DocumentStatus(str, PyEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FINAL = "final"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)  # optional link to the deal this document belongs to

    title = Column(String, nullable=False)
    doc_type = Column(Enum(DocumentType), nullable=False)
    source = Column(Enum(DocumentSource), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.DRAFT)

    content = Column(Text, nullable=False)          # current text content (plain text/markdown)
    original_content = Column(Text, nullable=True)   # snapshot before any rework, for comparison
    revision_count = Column(Integer, default=0)

    # Original uploaded file, if any — stored via file_storage_service.
    original_filename = Column(String, nullable=True)
    storage_file_id = Column(String, nullable=True)
    storage_file_extension = Column(String, nullable=True)

    # Compliance (fair housing) screening results — full LLM-backed screen,
    # since documents (especially disclosure drafts) warrant the deeper pass,
    # unlike the fast keyword-only check used for bulk listing ingestion.
    compliance_risk = Column(String, nullable=True)
    compliance_flags = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
