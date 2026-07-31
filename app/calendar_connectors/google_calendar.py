"""
Google Calendar connector. Real API (googleapis.com/calendar/v3), OAuth2.
Polling-based sync (events.list with timeMin/timeMax); events.watch push
notifications are a documented future upgrade (see gmail.py's docstring
for the same trade-off reasoning — watch channels need renewal handling).
"""
from datetime import datetime, timezone

import httpx

from app.services.oauth_token_service import get_valid_access_token

BASE_URL = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarConnector:
    def __init__(self, encrypted_tokens: str, calendar_id: str = "primary"):
        self.calendar_id = calendar_id
        self.access_token, self.refreshed_tokens = get_valid_access_token(encrypted_tokens, "gmail")  # same Google OAuth grant as Gmail

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.get(f"/calendars/{self.calendar_id}/events", params={
                "timeMin": time_min.isoformat() + "Z",
                "timeMax": time_max.isoformat() + "Z",
                "singleEvents": "true",
                "orderBy": "startTime",
            })
            resp.raise_for_status()
            return [self._normalize_event(e) for e in resp.json().get("items", [])]

    def create_event(self, event: dict) -> str:
        body = self._denormalize_event(event)
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.post(f"/calendars/{self.calendar_id}/events", json=body)
            resp.raise_for_status()
            return resp.json()["id"]

    def update_event(self, external_id: str, event: dict) -> None:
        body = self._denormalize_event(event)
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.patch(f"/calendars/{self.calendar_id}/events/{external_id}", json=body)
            resp.raise_for_status()

    def delete_event(self, external_id: str) -> None:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            client.delete(f"/calendars/{self.calendar_id}/events/{external_id}")

    def _normalize_event(self, raw: dict) -> dict:
        start = raw.get("start", {})
        end = raw.get("end", {})
        return {
            "external_id": raw["id"],
            "title": raw.get("summary", "(no title)"),
            "description": raw.get("description"),
            "location": raw.get("location"),
            "start_at": start.get("dateTime") or start.get("date"),
            "end_at": end.get("dateTime") or end.get("date"),
            "all_day": "date" in start and "dateTime" not in start,
            "attendees": [a.get("email") for a in raw.get("attendees", []) if a.get("email")],
        }

    def _denormalize_event(self, event: dict) -> dict:
        body = {
            "summary": event["title"],
            "description": event.get("description"),
            "location": event.get("location"),
        }
        if event.get("all_day"):
            body["start"] = {"date": event["start_at"][:10]}
            body["end"] = {"date": event["end_at"][:10]}
        else:
            body["start"] = {"dateTime": event["start_at"]}
            body["end"] = {"dateTime": event["end_at"]}
        if event.get("attendees"):
            body["attendees"] = [{"email": a} for a in event["attendees"]]
        return body
