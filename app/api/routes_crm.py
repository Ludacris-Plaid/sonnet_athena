"""
CRM connection management, manual sync trigger, sync history, CSV import,
and the webhook receiver that lets connected CRMs push real-time updates.
"""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.crm_connection import CRMConnection, CRMSyncLog
from app.schemas.crm import CRMConnectionCreate, CRMConnectionOut, CRMSyncLogOut
from app.services.crm_credential_service import encrypt_credentials, decrypt_credentials
from app.services.crm_sync_service import run_sync, handle_webhook_contact_update
from app.services.csv_import_service import import_csv
from app.crm_connectors.factory import get_connector

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/providers")
def list_providers(user: User = Depends(get_current_user)):
    return [
        {"key": "followupboss", "label": "Follow Up Boss", "credential_fields": ["api_key"], "supports_webhooks": True},
        {"key": "hubspot", "label": "HubSpot", "credential_fields": ["access_token"], "supports_webhooks": False},
    ]


@router.post("/connections", response_model=CRMConnectionOut)
def create_connection(payload: CRMConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.provider not in ("followupboss", "hubspot"):
        raise HTTPException(status_code=400, detail="Unsupported provider — use the CSV import endpoint instead")

    # Validate credentials actually work before saving them.
    try:
        connector = get_connector(payload.provider, payload.credentials)
        if not connector.test_connection():
            raise HTTPException(status_code=400, detail="Could not connect with the provided credentials")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    connection = CRMConnection(
        org_id=user.org_id,
        user_id=user.id,
        provider=payload.provider,
        sync_direction=payload.sync_direction,
        encrypted_credentials=encrypt_credentials(payload.credentials),
        webhook_secret=secrets.token_urlsafe(24),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/connections", response_model=list[CRMConnectionOut])
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(CRMConnection).filter(CRMConnection.org_id == user.org_id).all()


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(CRMConnection).filter(CRMConnection.id == connection_id, CRMConnection.org_id == user.org_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(conn)
    db.commit()
    return {"ok": True}


@router.post("/connections/{connection_id}/sync", response_model=CRMSyncLogOut)
def trigger_sync(connection_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(CRMConnection).filter(CRMConnection.id == connection_id, CRMConnection.org_id == user.org_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return run_sync(db, conn, trigger="manual")


@router.get("/connections/{connection_id}/logs", response_model=list[CRMSyncLogOut])
def list_sync_logs(connection_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(CRMConnection).filter(CRMConnection.id == connection_id, CRMConnection.org_id == user.org_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return (
        db.query(CRMSyncLog)
        .filter(CRMSyncLog.connection_id == connection_id)
        .order_by(CRMSyncLog.started_at.desc())
        .limit(20)
        .all()
    )


@router.post("/import/csv")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file upload")
    return import_csv(db, str(user.org_id), str(user.id), file_bytes)


@router.post("/webhook/{connection_id}/{webhook_secret}")
async def receive_webhook(connection_id: UUID, webhook_secret: str, request: Request, db: Session = Depends(get_db)):
    """
    No auth dependency here deliberately — this is called BY the external
    CRM, not by a logged-in RealtyAI user. The path-embedded secret is the
    verification layer (plus provider-specific signature checks where
    supported — see CRMConnector.verify_webhook_signature).
    """
    conn = db.query(CRMConnection).filter(CRMConnection.id == connection_id).first()
    if not conn or not secrets.compare_digest(conn.webhook_secret, webhook_secret):
        raise HTTPException(status_code=404, detail="Not found")  # deliberately vague — don't confirm connection existence to a bad guess

    raw_body = await request.body()
    payload = await request.json()

    credentials = decrypt_credentials(conn.encrypted_credentials)
    connector = get_connector(conn.provider.value, credentials)

    if not connector.verify_webhook_signature(dict(request.headers), raw_body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    contact_refs = connector.parse_webhook_event(payload)
    for ref in contact_refs:
        handle_webhook_contact_update(db, conn, ref)

    return {"ok": True, "processed": len(contact_refs)}
