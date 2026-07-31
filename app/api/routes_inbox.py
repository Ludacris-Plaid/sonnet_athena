"""
Unified inbox: list messages, generate draft replies, send a reply
(subject to the trust ladder).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User
from app.models.message import Message, Channel, MessageDirection
from app.services.inbox_service import generate_drafts, send_reply, send_new_message, resolve_action_type_for_channel
from app.services import trust_service
from app.services import client_service

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboundMessageCreate(BaseModel):
    channel: Channel
    client_id: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    subject: str | None = None
    body: str


class SendReplyRequest(BaseModel):
    chosen_body: str
    was_edited: bool = False


class SendNewMessageRequest(BaseModel):
    channel: Channel
    to_address: str
    body: str
    client_id: str | None = None
    subject: str | None = None


@router.get("")
def list_messages(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Message)
        .filter(Message.org_id == user.org_id)
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )


@router.post("/receive")
def receive_message(payload: InboundMessageCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Simulates an inbound webhook (Gmail push notification / Twilio SMS webhook
    would call an equivalent endpoint in production). Automatically generates
    draft replies once the message lands.
    """
    msg = Message(
        org_id=user.org_id,
        user_id=user.id,
        client_id=payload.client_id,
        channel=payload.channel,
        direction=MessageDirection.INBOUND,
        from_address=payload.from_address,
        to_address=payload.to_address,
        subject=payload.subject,
        body=payload.body,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    if msg.client_id:
        client_service.touch_last_contacted(db, str(msg.client_id))

    drafts = generate_drafts(db, msg, tones=["professional", "warm", "brief", "urgent"])

    action_type = resolve_action_type_for_channel(payload.channel.value)
    autonomous = trust_service.can_act_autonomously(db, str(user.id), action_type)

    return {"message": msg, "drafts": drafts, "athena_can_send_autonomously": autonomous}


@router.post("/{message_id}/reply")
def reply(message_id: UUID, payload: SendReplyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inbound = db.query(Message).filter(Message.id == message_id, Message.org_id == user.org_id).first()
    if not inbound:
        raise HTTPException(status_code=404, detail="Message not found")

    outbound = send_reply(db, inbound, payload.chosen_body, str(user.id), payload.was_edited)
    return outbound


@router.post("/send-new")
def send_new(payload: SendNewMessageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Send a message that isn't a reply to a pending inbound one — proactive
    outreach, or following up in a thread that's already been answered.
    This is what makes the Inbox composer work like a real chat box: type
    and send any time, not only when there's literally something to reply to.
    """
    outbound = send_new_message(
        db, str(user.org_id), str(user.id), payload.channel, payload.to_address,
        payload.body, payload.client_id, payload.subject,
    )
    return outbound


@router.post("/{message_id}/generate-drafts")
def generate_drafts_route(message_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    For any inbound message that doesn't have drafts yet — messages that
    arrived through a path other than the /receive simulation (a real
    Gmail/Twilio webhook, a CSV-imported history, etc.) won't have
    Athena's draft replies pre-generated. This is the "Create draft"
    button's endpoint — generates them on demand for an existing message.
    """
    msg = db.query(Message).filter(Message.id == message_id, Message.org_id == user.org_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.direction != MessageDirection.INBOUND:
        raise HTTPException(status_code=400, detail="Can only generate drafts for inbound messages")

    drafts = generate_drafts(db, msg, tones=["professional", "warm", "brief", "urgent"])
    return {"drafts": drafts}
