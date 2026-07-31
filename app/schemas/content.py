from pydantic import BaseModel


class ContentGenerateRequest(BaseModel):
    property_id: str
    content_types: list[str]


class ContentItemOut(BaseModel):
    content_type: str
    label: str | None = None
    content: str | None = None
    compliance_risk: str | None = None
    compliance_flags: list | None = None
    error: str | None = None
