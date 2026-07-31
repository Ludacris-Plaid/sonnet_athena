"""
Two-way sync between CalendarEvent (local) and Google/Microsoft Calendar.
Pull: remote events upserted into CalendarEvent, matched by external_id.
Push: local events with sync_pending=True get created/updated remotely.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent, CalendarConnection, CalendarProvider
from app.calendar_connectors.google_calendar import GoogleCalendarConnector
from app.calendar_connectors.microsoft_calendar import MicrosoftCalendarConnector
from app.services.crm_credential_service import decrypt_credentials, encrypt_credentials


def _get_connector(connection: CalendarConnection):
    if connection.provider == CalendarProvider.GOOGLE:
        return GoogleCalendarConnector(connection.encrypted_tokens, connection.calendar_id)
    return MicrosoftCalendarConnector(connection.encrypted_tokens)


def sync_connection(db: Session, connection: CalendarConnection, window_days: int = 60) -> dict:
    connector = _get_connector(connection)
    pulled = pushed = 0

    if connection.sync_direction in ("import_only", "two_way"):
        time_min = datetime.now(timezone.utc) - timedelta(days=7)
        time_max = datetime.now(timezone.utc) + timedelta(days=window_days)
        remote_events = connector.list_events(time_min, time_max)

        for re_ in remote_events:
            existing = (
                db.query(CalendarEvent)
                .filter(CalendarEvent.org_id == connection.org_id, CalendarEvent.external_id == re_["external_id"])
                .first()
            )
            if existing:
                existing.title = re_["title"]
                existing.description = re_.get("description")
                existing.location = re_.get("location")
                existing.start_at = re_["start_at"]
                existing.end_at = re_["end_at"]
                existing.last_synced_at = datetime.now(timezone.utc)
                db.add(existing)
            else:
                db.add(CalendarEvent(
                    org_id=connection.org_id, user_id=connection.user_id,
                    title=re_["title"], description=re_.get("description"), location=re_.get("location"),
                    start_at=re_["start_at"], end_at=re_["end_at"], all_day=re_.get("all_day", False),
                    provider=connection.provider, external_id=re_["external_id"],
                    attendees=re_.get("attendees"), last_synced_at=datetime.now(timezone.utc),
                ))
            pulled += 1

    if connection.sync_direction in ("export_only", "two_way"):
        pending = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.org_id == connection.org_id, CalendarEvent.sync_pending == True)  # noqa: E712
            .all()
        )
        for event in pending:
            event_dict = {
                "title": event.title, "description": event.description, "location": event.location,
                "start_at": event.start_at.isoformat(), "end_at": event.end_at.isoformat(),
                "all_day": event.all_day, "attendees": event.attendees,
            }
            if event.external_id:
                connector.update_event(event.external_id, event_dict)
            else:
                event.external_id = connector.create_event(event_dict)
                event.provider = connection.provider
            event.sync_pending = False
            event.last_synced_at = datetime.now(timezone.utc)
            db.add(event)
            pushed += 1

    connection.last_synced_at = datetime.now(timezone.utc)
    connection.last_sync_status = "success"
    db.add(connection)

    if connector.refreshed_tokens:
        connection.encrypted_tokens = connector.refreshed_tokens
        db.add(connection)

    db.commit()
    return {"pulled": pulled, "pushed": pushed}
