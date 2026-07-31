"""
Document management: import + extract, generate from scratch, score
(full LLM-backed compliance review — documents warrant the deeper pass,
unlike bulk listing ingestion), and rework to resolve flagged issues.
"""
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentType, DocumentSource, DocumentStatus
from app.services.document_extraction_service import extract_text
from app.services.file_storage_service import save_file
from app.services.compliance_service import screen_listing_text
from app.services.llm_service import llm_service
from app.prompts.document_prompts import GENERATION_SYSTEM_PROMPT, build_generation_prompt, REWORK_SYSTEM_PROMPT, build_rework_prompt


def upload_document(db: Session, org_id: str, user_id: str, file_bytes: bytes, filename: str, doc_type: str) -> Document:
    content = extract_text(file_bytes, filename)
    if not content.strip():
        raise ValueError("No extractable text found in this file.")

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "bin"
    storage_file_id = save_file(file_bytes, ext)

    doc = Document(
        org_id=org_id,
        user_id=user_id,
        title=filename,
        doc_type=doc_type,
        source=DocumentSource.UPLOADED,
        status=DocumentStatus.DRAFT,
        content=content,
        original_content=content,
        original_filename=filename,
        storage_file_id=storage_file_id,
        storage_file_extension=ext,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _score_and_save(db, doc)
    return doc


def generate_document(db: Session, org_id: str, user_id: str, title: str, doc_type: str, instructions: str | None = None, context: str | None = None) -> Document:
    prompt = build_generation_prompt(doc_type, instructions, context)
    response = llm_service.complete(GENERATION_SYSTEM_PROMPT, prompt, temperature=0.5, max_tokens=1200)
    content = response.text.strip()

    doc = Document(
        org_id=org_id,
        user_id=user_id,
        title=title,
        doc_type=doc_type,
        source=DocumentSource.GENERATED,
        status=DocumentStatus.DRAFT,
        content=content,
        original_content=content,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _score_and_save(db, doc)
    return doc


def score_document(db: Session, document_id: str) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")
    _score_and_save(db, doc)
    return doc


def rework_document(db: Session, document_id: str, extra_instructions: str | None = None) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError("Document not found")

    flags = doc.compliance_flags or []
    if not flags and not extra_instructions:
        # Nothing flagged and no new instructions — re-score to make sure
        # that's still accurate, but don't burn an LLM rewrite call for
        # nothing.
        _score_and_save(db, doc)
        return doc

    prompt = build_rework_prompt(doc.content, flags, extra_instructions)
    response = llm_service.complete(REWORK_SYSTEM_PROMPT, prompt, temperature=0.3, max_tokens=1500)

    doc.content = response.text.strip()
    doc.revision_count = (doc.revision_count or 0) + 1
    doc.status = DocumentStatus.DRAFT
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _score_and_save(db, doc)
    return doc


def _score_and_save(db: Session, doc: Document) -> None:
    result = screen_listing_text(doc.content)
    doc.compliance_risk = result["overall_risk"]
    doc.compliance_flags = result["flags"]
    if result["overall_risk"] == "low" and doc.status == DocumentStatus.DRAFT:
        doc.status = DocumentStatus.REVIEWED
    db.add(doc)
    db.commit()
    db.refresh(doc)
