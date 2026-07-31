"""
OAuth flows for Google/Microsoft (email + calendar), Slack Events API
webhook, and Twilio SMS webhook. Grouped together since they're all
"external service talks to us" surfaces with a similar shape: verify the
request is legitimate, then hand off to the right service.
"""
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.org import User, Organization
from app.models.email_connection import EmailConnection, EmailProvider, SlackConnection
from app.models.calendar_event import CalendarConnection, CalendarProvider
from app.models.message import Message, Channel, MessageDirection
from app.services.oauth_token_service import exchange_google_code, exchange_microsoft_code
from app.services.crm_credential_service import encrypt_credentials
from app.services.email_sync_service import sync_connection as sync_email_connection
from app.services.calendar_sync_service import sync_connection as sync_calendar_connection
from app.services.slack_service import verify_slack_signature, handle_event as handle_slack_event

router = APIRouter(prefix="/integrations", tags=["integrations"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar"
MICROSOFT_SCOPES = "offline_access Mail.Read Mail.Send Calendars.ReadWrite"


# ---------------------------------------------------------------------------
# Google OAuth (covers both Gmail and Google Calendar — one consent screen)
# ---------------------------------------------------------------------------

@router.get("/google/authorize")
def google_authorize(user: User = Depends(get_current_user)):
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",   # required to get a refresh_token
        "prompt": "consent",        # forces refresh_token on every auth, not just the first
        "state": str(user.id),      # naive state — for production, sign/verify this against a stored nonce
    }
    return {"authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/google/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == state).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid state")

    tokens = exchange_google_code(code)
    encrypted = encrypt_credentials(tokens)

    # One Google auth grants both Gmail and Calendar scopes — create both connection rows.
    email_conn = db.query(EmailConnection).filter(EmailConnection.user_id == user.id, EmailConnection.provider == EmailProvider.GMAIL).first()
    if email_conn:
        email_conn.encrypted_tokens = encrypted
    else:
        email_conn = EmailConnection(org_id=user.org_id, user_id=user.id, provider=EmailProvider.GMAIL, email_address=user.email, encrypted_tokens=encrypted)
    db.add(email_conn)

    cal_conn = db.query(CalendarConnection).filter(CalendarConnection.user_id == user.id, CalendarConnection.provider == CalendarProvider.GOOGLE).first()
    if cal_conn:
        cal_conn.encrypted_tokens = encrypted
    else:
        cal_conn = CalendarConnection(org_id=user.org_id, user_id=user.id, provider=CalendarProvider.GOOGLE, encrypted_tokens=encrypted)
    db.add(cal_conn)
    db.commit()

    return RedirectResponse(url="/app/integrations.html?connected=google")


# ---------------------------------------------------------------------------
# Microsoft OAuth (covers Outlook Mail + Calendar)
# ---------------------------------------------------------------------------

@router.get("/microsoft/authorize")
def microsoft_authorize(user: User = Depends(get_current_user)):
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "scope": MICROSOFT_SCOPES,
        "state": str(user.id),
    }
    url = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize?{urlencode(params)}"
    return {"authorize_url": url}


@router.get("/microsoft/callback")
def microsoft_callback(code: str, state: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == state).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid state")

    tokens = exchange_microsoft_code(code)
    encrypted = encrypt_credentials(tokens)

    email_conn = db.query(EmailConnection).filter(EmailConnection.user_id == user.id, EmailConnection.provider == EmailProvider.MICROSOFT).first()
    if email_conn:
        email_conn.encrypted_tokens = encrypted
    else:
        email_conn = EmailConnection(org_id=user.org_id, user_id=user.id, provider=EmailProvider.MICROSOFT, email_address=user.email, encrypted_tokens=encrypted)
    db.add(email_conn)

    cal_conn = db.query(CalendarConnection).filter(CalendarConnection.user_id == user.id, CalendarConnection.provider == CalendarProvider.MICROSOFT).first()
    if cal_conn:
        cal_conn.encrypted_tokens = encrypted
    else:
        cal_conn = CalendarConnection(org_id=user.org_id, user_id=user.id, provider=CalendarProvider.MICROSOFT, encrypted_tokens=encrypted)
    db.add(cal_conn)
    db.commit()

    return RedirectResponse(url="/app/integrations.html?connected=microsoft")


# ---------------------------------------------------------------------------
# Connection management + manual sync triggers
# ---------------------------------------------------------------------------

@router.get("/connections")
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emails = db.query(EmailConnection).filter(EmailConnection.org_id == user.org_id).all()
    calendars = db.query(CalendarConnection).filter(CalendarConnection.org_id == user.org_id).all()
    slack = db.query(SlackConnection).filter(SlackConnection.org_id == user.org_id).first()
    return {
        "email": [{"id": str(e.id), "provider": e.provider.value, "email_address": e.email_address, "last_synced_at": e.last_synced_at} for e in emails],
        "calendar": [{"id": str(c.id), "provider": c.provider.value, "last_synced_at": c.last_synced_at} for c in calendars],
        "slack": {"connected": slack is not None, "team_name": slack.team_name if slack else None} if slack else {"connected": False},
    }


@router.post("/email/{connection_id}/sync")
def sync_email(connection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(EmailConnection).filter(EmailConnection.id == connection_id, EmailConnection.org_id == user.org_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return sync_email_connection(db, conn)


@router.post("/calendar/{connection_id}/sync")
def sync_calendar(connection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(CalendarConnection).filter(CalendarConnection.id == connection_id, CalendarConnection.org_id == user.org_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return sync_calendar_connection(db, conn)


# ---------------------------------------------------------------------------
# Slack — connect (paste bot token manually; simplest reliable path without
# building a full Slack App Directory listing) + events webhook
# ---------------------------------------------------------------------------

@router.post("/slack/connect")
def connect_slack(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """payload: {"bot_token": "xoxb-...", "team_id": "...", "notification_channel_id": "..."}"""
    encrypted = encrypt_credentials({"bot_token": payload["bot_token"]})
    conn = db.query(SlackConnection).filter(SlackConnection.org_id == user.org_id).first()
    if conn:
        conn.encrypted_tokens = encrypted
        conn.notification_channel_id = payload.get("notification_channel_id")
    else:
        conn = SlackConnection(
            org_id=user.org_id, team_id=payload.get("team_id", ""), team_name=payload.get("team_name"),
            encrypted_tokens=encrypted, notification_channel_id=payload.get("notification_channel_id"),
        )
    db.add(conn)
    db.commit()
    return {"ok": True}


@router.post("/slack/events")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    if not verify_slack_signature(dict(request.headers), raw_body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()

    if payload.get("type") == "url_verification":  # Slack's setup handshake
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    if event.get("type") in ("app_mention", "message") and not event.get("bot_id"):
        connection = db.query(SlackConnection).filter(SlackConnection.team_id == payload.get("team_id")).first()
        if connection:
            default_user = db.query(User).filter(User.org_id == connection.org_id, User.is_admin == False).first()  # noqa: E712
            if default_user:
                handle_slack_event(db, connection, event, str(connection.org_id), str(default_user.id))

    return {"ok": True}


# ---------------------------------------------------------------------------
# Twilio SMS webhook (inbound texts to the business number)
# ---------------------------------------------------------------------------

@router.post("/twilio/sms")
async def twilio_sms(request: Request, db: Session = Depends(get_db)):
    from fastapi import Form
    form = await request.form()
    from_number = form.get("From", "")
    body_text = form.get("Body", "")

    user = db.query(User).filter(User.is_admin == True).first()  # noqa: E712 — same single-tenant routing caveat as routes_voice_telephony.py
    if not user:
        return {"ok": False}

    msg = Message(
        org_id=user.org_id, user_id=user.id, channel=Channel.SMS,
        direction=MessageDirection.INBOUND, from_address=from_number, body=body_text,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    from app.services.inbox_service import generate_drafts
    generate_drafts(db, msg, tones=["professional", "warm", "brief", "urgent"])

    # Twilio expects TwiML (or an empty 200) in response — an empty response
    # means "don't auto-reply," which is correct here since replies go
    # through the normal draft-approval flow in the Inbox, same as any
    # other SMS. Auto-sending would bypass the trust ladder entirely.
    from fastapi.responses import Response
    return Response(content="<Response></Response>", media_type="application/xml")
