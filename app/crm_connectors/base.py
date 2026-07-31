"""
Common interface every CRM connector implements. This mirrors the
ListingsSource pattern already in the codebase (app/scrapers/base.py) —
same reasoning: the rest of the system should never need to know which CRM
it's talking to.

Contact shape returned by list_contacts() / expected by
create_or_update_contact() is normalized to RealtyAI's own field names:
    {
        "external_id": str,
        "name": str,
        "email": str | None,
        "phone": str | None,
        "client_type": "buyer" | "seller" | "both",
        "budget_max": float | None,
        "preferred_city": str | None,
        "notes": str | None,
    }
"""
from abc import ABC, abstractmethod


class CRMConnector(ABC):
    def __init__(self, credentials: dict):
        self.credentials = credentials

    @abstractmethod
    def test_connection(self) -> bool:
        """Returns True if the credentials are valid and the API is reachable."""
        raise NotImplementedError

    @abstractmethod
    def list_contacts(self, since: str | None = None) -> list[dict]:
        """
        Pull contacts from the CRM, normalized to RealtyAI's contact shape.
        `since` is an ISO timestamp for incremental sync, where supported.
        """
        raise NotImplementedError

    @abstractmethod
    def create_or_update_contact(self, contact: dict) -> str:
        """
        Push a RealtyAI client to the CRM. Returns the CRM's external_id
        for the created/updated record, so it can be stored back on Client.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_webhook_event(self, payload: dict) -> list[dict]:
        """
        Normalize an inbound webhook payload into a list of contact dicts
        (usually one, but some providers batch events). Returns [] for
        event types that aren't contact-related (e.g. a note or task event).
        """
        raise NotImplementedError

    def verify_webhook_signature(self, headers: dict, raw_body: bytes) -> bool:
        """
        Provider-specific signature verification, if the provider supports
        it. Default: no additional check beyond the per-connection secret
        already in the webhook URL — override in connectors that support
        HMAC signatures for a real second layer of verification.
        """
        return True
