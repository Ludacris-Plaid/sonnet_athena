"""
HubSpot connector. Real API, CRM v3 REST endpoints.

Auth: Private App access token (Bearer), generated per-account under
Settings -> Integrations -> Private Apps in the realtor's own HubSpot
account. This is the right choice for a single-account integration like
this one — OAuth is only needed for a public Marketplace app serving many
HubSpot accounts, which brings a review process this doesn't need.

Base URL: https://api.hubapi.com
Rate limit: 100 requests / 10 seconds per portal on most tiers (190/10s on
Pro+). Not implemented here as a hard client-side throttle — HubSpot
returns 429 on breach, which httpx surfaces as an HTTPStatusError; add
retry/backoff (tenacity, already a dependency) if you hit this in practice
with larger contact lists.

Webhooks require a public Marketplace app (not available to private apps
via the API) — see the note in crm_sync_service.py. For most realtors using
a Private App token, polling via /crm/v3/objects/contacts with the
lastmodifieddate property is the practical sync path, not webhooks.
"""
import httpx

from app.crm_connectors.base import CRMConnector

BASE_URL = "https://api.hubapi.com"
CONTACT_PROPERTIES = ["firstname", "lastname", "email", "phone", "lifecyclestage", "hs_lead_status"]


class HubSpotConnector(CRMConnector):
    def __init__(self, credentials: dict):
        super().__init__(credentials)
        self.access_token = credentials.get("access_token", "")
        if not self.access_token:
            raise ValueError("HubSpot connector requires 'access_token' (Private App token) in credentials")

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )

    def test_connection(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get("/crm/v3/objects/contacts", params={"limit": 1})
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_contacts(self, since: str | None = None) -> list[dict]:
        contacts = []
        params = {"limit": 100, "properties": ",".join(CONTACT_PROPERTIES)}
        after = None

        with self._client() as client:
            while True:
                if after:
                    params["after"] = after
                resp = client.get("/crm/v3/objects/contacts", params=params)
                resp.raise_for_status()
                data = resp.json()

                for record in data.get("results", []):
                    contacts.append(self._normalize_contact(record))

                paging = data.get("paging", {}).get("next", {})
                after = paging.get("after")
                if not after:
                    break

        return contacts

    def create_or_update_contact(self, contact: dict) -> str:
        properties = self._denormalize_contact(contact)
        with self._client() as client:
            if contact.get("external_id"):
                resp = client.patch(
                    f"/crm/v3/objects/contacts/{contact['external_id']}",
                    json={"properties": properties},
                )
                resp.raise_for_status()
                return str(resp.json()["id"])

            resp = client.post("/crm/v3/objects/contacts", json={"properties": properties})
            resp.raise_for_status()
            return str(resp.json()["id"])

    def parse_webhook_event(self, payload: dict) -> list[dict]:
        # Only relevant if a public Marketplace app is used — see module
        # docstring. HubSpot sends a LIST of event objects, each referencing
        # an objectId; like FUB, the payload is lightweight and the full
        # record is fetched separately.
        events = payload if isinstance(payload, list) else [payload]
        results = []
        for event in events:
            if event.get("subscriptionType", "").startswith("contact."):
                results.append({"external_id": str(event.get("objectId")), "_needs_fetch": True})
        return results

    def fetch_contact_by_id(self, external_id: str) -> dict | None:
        with self._client() as client:
            resp = client.get(
                f"/crm/v3/objects/contacts/{external_id}",
                params={"properties": ",".join(CONTACT_PROPERTIES)},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._normalize_contact(resp.json())

    def _normalize_contact(self, record: dict) -> dict:
        props = record.get("properties", {})
        name = f"{props.get('firstname') or ''} {props.get('lastname') or ''}".strip() or "Unknown"
        return {
            "external_id": str(record.get("id")),
            "name": name,
            "email": props.get("email"),
            "phone": props.get("phone"),
            "client_type": "buyer",  # HubSpot has no real-estate-specific buyer/seller field by default
            "budget_max": None,
            "preferred_city": None,
            "notes": props.get("hs_lead_status"),
        }

    def _denormalize_contact(self, contact: dict) -> dict:
        name_parts = (contact.get("name") or "").split(" ", 1)
        props = {"firstname": name_parts[0] if name_parts else ""}
        if len(name_parts) > 1:
            props["lastname"] = name_parts[1]
        if contact.get("email"):
            props["email"] = contact["email"]
        if contact.get("phone"):
            props["phone"] = contact["phone"]
        return props
