"""Microsoft/Outlook Calendar connector via Graph API. Real endpoints, OAuth2."""
from datetime import datetime

import httpx

from app.services.oauth_token_service import get_valid_access_token

BASE_URL = "https://graph.microsoft.com/v1.0"


class MicrosoftCalendarConnector:
    def __init__(self, encrypted_tokens: str):
        self.access_token, self.refreshed_tokens = get_valid_access_token(encrypted_tokens, "microsoft")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def list_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.get("/me/calendarView", params={
                "startDateTime": time_min.isoformat(),
                "endDateTime": time_max.isoformat(),
            })
            resp.raise_for_status()
            return [self._normalize_event(e) for e in resp.json().get("value", [])]

    def create_event(self, event: dict) -> str:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.post("/me/events", json=self._denormalize_event(event))
            resp.raise_for_status()
            return resp.json()["id"]

    def update_event(self, external_id: str, event: dict) -> None:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.patch(f"/me/events/{external_id}", json=self._denormalize_event(event))
            resp.raise_for_status()

    def delete_event(self, external_id: str) -> None:
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            client.delete(f"/me/events/{external_id}")

    def _normalize_event(self, raw: dict) -> dict:
        return {
            "external_id": raw.get("id"),
            "title": raw.get("subject", "(no title)"),
            "description": (raw.get("bodyPreview") or ""),
            "location": (raw.get("location", {}) or {}).get("displayName"),
            "start_at": raw.get("start", {}).get("dateTime"),
            "end_at": raw.get("end", {}).get("dateTime"),
            "all_day": raw.get("isAllDay", False),
            "attendees": [a.get("emailAddress", {}).get("address") for a in raw.get("attendees", [])],
        }

    def _denormalize_event(self, event: dict) -> dict:
        body = {
            "subject": event["title"],
            "body": {"contentType": "Text", "content": event.get("description") or ""},
            "start": {"dateTime": event["start_at"], "timeZone": "UTC"},
            "end": {"dateTime": event["end_at"], "timeZone": "UTC"},
            "isAllDay": event.get("all_day", False),
        }
        if event.get("location"):
            body["location"] = {"displayName": event["location"]}
        if event.get("attendees"):
            body["attendees"] = [{"emailAddress": {"address": a}} for a in event["attendees"]]
        return body
