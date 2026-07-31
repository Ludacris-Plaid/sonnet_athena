"""
Microsoft Outlook/Exchange connector via Microsoft Graph. Real API
(graph.microsoft.com/v1.0), OAuth2. Simpler than Gmail here — Graph's
/me/messages returns full message content directly, no separate get call
needed per message.

Incremental sync uses delta queries ($deltaToken) — Microsoft Graph mail
subscriptions for push notifications expire ~3 days and need renewal, same
caveat as Gmail: this connector polls, push notifications are a documented
future upgrade, not implemented here.
"""
import httpx

from app.services.oauth_token_service import get_valid_access_token

BASE_URL = "https://graph.microsoft.com/v1.0"


class MicrosoftEmailConnector:
    def __init__(self, encrypted_tokens: str):
        self.encrypted_tokens = encrypted_tokens
        self.access_token, self.refreshed_tokens = get_valid_access_token(encrypted_tokens, "microsoft")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_new_messages(self, delta_link: str | None = None, max_results: int = 20) -> tuple[list[dict], str | None]:
        url = delta_link or f"{BASE_URL}/me/mailFolders/inbox/messages/delta"
        params = None if delta_link else {"$top": max_results}

        with httpx.Client(headers=self._headers(), timeout=30) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        messages = [self._normalize_message(m) for m in data.get("value", []) if "@removed" not in m]
        new_delta_link = data.get("@odata.deltaLink", delta_link)
        return messages, new_delta_link

    def send_message(self, to: str, subject: str, body: str) -> None:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }
        }
        with httpx.Client(base_url=BASE_URL, headers=self._headers(), timeout=30) as client:
            resp = client.post("/me/sendMail", json=payload)
            resp.raise_for_status()

    def _normalize_message(self, raw: dict) -> dict:
        return {
            "external_id": raw.get("id"),
            "from_address": (raw.get("from", {}).get("emailAddress", {}) or {}).get("address"),
            "to_address": ", ".join(r.get("emailAddress", {}).get("address", "") for r in raw.get("toRecipients", [])),
            "subject": raw.get("subject"),
            "body": (raw.get("bodyPreview") or ""),
        }
