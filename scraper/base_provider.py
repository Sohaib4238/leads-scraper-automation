"""
Abstract base class for discovery providers.

All providers return leads in a standardized dict format matching the Lead model,
plus a _raw_tags dict with normalized contact keys (Fix #1).
"""

from abc import ABC, abstractmethod


class DiscoveryProvider(ABC):
    """
    Pluggable interface for business discovery sources.

    Each provider searches for businesses in a city/category and returns
    a list of dicts with standardized fields.

    The _raw_tags dict uses normalized keys across all providers:
        - "contact:facebook"  -> Facebook page URL
        - "contact:instagram" -> Instagram profile URL
        - "contact:linkedin"  -> LinkedIn page URL
        - "contact:twitter"   -> Twitter/X profile URL
    This ensures the web_presence_resolver works identically regardless
    of which provider found the lead (Fix #1).
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Short identifier for this provider, e.g. 'osm', 'geoapify'."""
        ...

    @abstractmethod
    def search(
        self, country: str, city: str, category: str, count: int = 50
    ) -> list[dict]:
        """
        Search for businesses and return parsed lead dicts.

        Returns:
            List of dicts with keys matching Lead model fields, plus:
            - _raw_tags: dict of normalized contact tags for the resolver
            - _source: str identifying this provider (auto-set by base)
        """
        ...

    def _tag_results(self, results: list[dict]) -> list[dict]:
        """Tag each result with this provider's source name."""
        for r in results:
            r["_source"] = self.source_name
            if "_raw_tags" not in r:
                r["_raw_tags"] = {}
        return results
