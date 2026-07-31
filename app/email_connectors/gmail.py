"""
Gmail connector. Real API (gmail.googleapis.com/gmail/v1), OAuth2.

Note on quota: messages.list returns IDs only, not content — each message
needs a separate messages.get call. For an initial import of a large
mailbox this adds up fast (each get costs quota units); this connector
caps how many messages it pulls per call (`max_results`) rather than
draining the user's whole history in one request, and callers should page
across multiple calls for a full import instead of one huge one.

Push notifications (Pub/Sub watch) are NOT implemented here — Gmail watch
subscriptions expire every 7 days and need a renewal cron; this connector
uses polling instead (call list_new_messages periodically, e.g. every few
minutes, using the stored historyId for incremental sync). Wire up
watch()/Pub/Sub later if near-real-time delivery becomes a requirement —
documented as a real gap, not silently omitted.
"""
import base64
from email.mime.text import MIMEText

import httpx

from app.services.oauth_token_service import get_valid_access_token

BASE_URL = "https://gmail.googleapis.com/gmail/v1"


class GmailConnector:
    def __init__(self, encrypted_tokens: str):
        self.encrypted_tokens = encrypted_tokens
        self.access_token, self.refreshed_tokens = get_valid_access_token(encrypted_tokens, "gmail")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_new_messages(self, history_id: str | None = None, max_results: int = 20) -> tuple[list[dict], str | None]:
        """Returns (messages, new_history_id). If history_id is None, does an initial pull of recent messages instead of a history-based delta."""
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            if history_id:
                resp = client.get("/users/me/history", params={"startHistoryId": history_id, "historyTypes": "messageAdded"})
                resp.raise_for_status()
                data = resp.json()
                message_ids = [h["messages"][0]["id"] for h in data.get("history", []) if h.get("messages")]
                new_history_id = data.get("historyId", history_id)
            else:
                resp = client.get("/users/me/messages", params={"maxResults": max_results})
                resp.raise_for_status()
                data = resp.json()
                message_ids = [m["id"] for m in data.get("messages", [])]
                profile = client.get("/users/me/profile")
                new_history_id = profile.json().get("historyId") if profile.status_code == 200 else None

            messages = []
            for mid in message_ids[:max_results]:
                msg_resp = client.get(f"/users/me/messages/{mid}", params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject"]})
                if msg_resp.status_code != 200:
                    continue
                messages.append(self._normalize_message(msg_resp.json()))

        return messages, new_history_id

    def send_message(self, to: str, subject: str, body: str) -> str:
        mime = MIMEText(body)
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.post("/users/me/messages/send", json={"raw": raw})
            resp.raise_for_status()
            return resp.json()["id"]

    def _normalize_message(self, raw: dict) -> dict:
        headers = {h["name"]: h["value"] for h in raw.get("payload", {}).get("headers", [])}
        return {
            "external_id": raw["id"],
            "from_address": headers.get("From"),
            "to_address": headers.get("To"),
            "subject": headers.get("Subject"),
            "body": raw.get("snippet", ""),  # metadata format gives a snippet, not full body — fetch format=full for that if needed
        }
