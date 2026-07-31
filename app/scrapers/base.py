"""
Abstract interface for a listings data source. Every source (demo, RESO/MLS,
a future licensed API) implements this same interface so the rest of the
pipeline (ingestion, comps, scoring) never needs to know where data came from.
"""
from abc import ABC, abstractmethod


class ListingsSource(ABC):
    @abstractmethod
    def fetch_listings(self, city: str, state: str, limit: int = 50) -> list[dict]:
        """Return a list of normalized listing dicts. Shape must match
        the fields expected by app.models.property.Property."""
        raise NotImplementedError
