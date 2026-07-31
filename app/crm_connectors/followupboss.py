"""
Follow Up Boss connector. Real API, documented at followupboss.com/developers.

Auth: HTTP Basic Auth, API key as username, empty password.
Base URL: https://api.followupboss.com/v1
Rate limit: 1000 requests / 10-minute window per API key (429 on breach).

Notes on API design choices reflected here:
- New leads should go through POST /events (not POST /people directly) —
  Follow Up Boss's own docs recommend this so the contact triggers the
  account's configured automations, same as a real lead source would.
  Updates to EXISTING contacts use PUT /people/{id} directly.
- Webhooks: subscribes to peopleCreated/peopleUpdated. FUB webhook payloads
  contain the event type and person ID, but not the full person record —
  the payload just tells you what changed; you fetch the record via the API
  to get current data. parse_webhook_event() reflects that (it returns a
  lightweight reference, and crm_sync_service fetches the full record).
"""
import httpx

from app.crm_connectors.base import CRMConnector

BASE_URL = "https://api.followupboss.com/v1"


class FollowUpBossConnector(CRMConnector):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.api_key = credentials.get("api_key", "")
        if not self.api_key:
            raise ValueError("Follow Up Boss connector requires 'api_key' in credentials")

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=BASE_URL, auth=(self.api_key, ""), timeout=30)

    def test_connection(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get("/identity")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_contacts(self, since: str | None = None) -> list[dict]:
        contacts = []
        offset = 0
        limit = 100

        with self._client() as client:
            while True:
                params = {"limit": limit, "offset": offset}
                if since:
                    params["updated"] = since  # FUB supports filtering by updated timestamp on /people
                resp = client.get("/people", params=params)
                resp.raise_for_status()
                data = resp.json()
                people = data.get("people", [])
                contacts.extend(self._normalize_person(p) for p in people)

                if len(people) < limit:
                    break
                offset += limit

        return contacts

    def create_or_update_contact(self, contact: dict) -> str:
        with self._client() as client:
            if contact.get("external_id"):
                # Existing FUB person — update directly.
                resp = client.put(
                    f"/people/{contact['external_id']}",
                    json=self._denormalize_person(contact),
                )
                resp.raise_for_status()
                return str(resp.json()["id"])

            # New lead — go through /events so FUB's automations fire, per
            # their documented best practice (see module docstring).
            resp = client.post(
                "/events",
                json={
                    "person": self._denormalize_person(contact),
                    "type": "Registration",  # generic "new contact" event type
                    "source": "RealtyAI",
                },
            )
            resp.raise_for_status()
            return str(resp.json()["person"]["id"])

    def parse_webhook_event(self, payload: dict) -> list[dict]:
        event_type = payload.get("event", "")
        if not event_type.startswith("people"):
            return []  # not a contact event (e.g. notesCreated) — nothing to sync

        # FUB webhook payloads reference the changed person by ID under
        # resourceIds; the full record is fetched separately by the caller
        # (crm_sync_service) since the payload itself is lightweight.
        resource_ids = payload.get("resourceIds", [])
        return [{"external_id": str(rid), "_needs_fetch": True} for rid in resource_ids]

    def fetch_contact_by_id(self, external_id: str) -> dict | None:
        """Used by crm_sync_service after a webhook event to get the full record."""
        with self._client() as client:
            resp = client.get(f"/people/{external_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._normalize_person(resp.json())

    def _normalize_person(self, p: dict) -> dict:
        emails = p.get("emails") or []
        phones = p.get("phones") or []
        return {
            "external_id": str(p.get("id")),
            "name": f"{p.get('firstName', '')} {p.get('lastName', '')}".strip() or p.get("name", "Unknown"),
            "email": emails[0]["value"] if emails else None,
            "phone": phones[0]["value"] if phones else None,
            "client_type": "buyer" if p.get("stage", "").lower() != "seller" else "seller",
            "budget_max": None,  # FUB doesn't have a standard budget field; would need a custom field mapping
            "preferred_city": None,
            "notes": p.get("background"),
        }

    def _denormalize_person(self, contact: dict) -> dict:
        name_parts = (contact.get("name") or "").split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        payload = {"firstName": first_name, "lastName": last_name}
        if contact.get("email"):
            payload["emails"] = [{"value": contact["email"]}]
        if contact.get("phone"):
            payload["phones"] = [{"value": contact["phone"]}]
        return payload
