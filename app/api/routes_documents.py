from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.document import Document, DocumentType
from app.schemas.document import DocumentOut, DocumentGenerateRequest, DocumentReworkRequest
from app.services.document_service import upload_document, generate_document, score_document, rework_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/types")
def list_document_types(user: User = Depends(get_current_user)):
    return [t.value for t in DocumentType]


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Document).filter(Document.org_id == user.org_id).order_by(Document.updated_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == document_id, Document.org_id == user.org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/upload", response_model=DocumentOut)
async def upload(
    file: UploadFile = File(...),
    doc_type: str = Form("uploaded_other"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload")
    try:
        return upload_document(db, str(user.org_id), str(user.id), file_bytes, file.filename or "upload", doc_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate", response_model=DocumentOut)
def generate(payload: DocumentGenerateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return generate_document(
        db, str(user.org_id), str(user.id), payload.title, payload.doc_type, payload.instructions, payload.context
    )


@router.post("/{document_id}/score", response_model=DocumentOut)
def score(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == document_id, Document.org_id == user.org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return score_document(db, str(document_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{document_id}/rework", response_model=DocumentOut)
def rework(document_id: UUID, payload: DocumentReworkRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == document_id, Document.org_id == user.org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return rework_document(db, str(document_id), payload.instructions)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
