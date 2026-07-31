from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    doc_type: str
    source: str
    status: str
    content: str
    revision_count: int
    original_filename: Optional[str] = None
    compliance_risk: Optional[str] = None
    compliance_flags: Optional[list] = None
    created_at: datetime
    updated_at: datetime


class DocumentGenerateRequest(BaseModel):
    title: str
    doc_type: str
    instructions: Optional[str] = None
    context: Optional[str] = None


class DocumentReworkRequest(BaseModel):
    instructions: Optional[str] = None
