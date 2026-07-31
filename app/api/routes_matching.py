from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.client import Client
from app.models.property import Property
from app.services.matching_service import match_properties_for_client, find_clients_for_new_listing

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/clients/{client_id}/properties")
def properties_for_client(client_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return match_properties_for_client(db, client)


@router.get("/properties/{property_id}/clients")
def clients_for_property(property_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prop = db.query(Property).filter(Property.id == property_id, Property.org_id == user.org_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return find_clients_for_new_listing(db, prop)
