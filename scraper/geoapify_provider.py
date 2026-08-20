"""
Geoapify Places API discovery provider.

Uses Geocoding API to resolve city -> place_id, then Places API to search.
Standardizes _raw_tags format so resolver works identically (Fix #1).
"""

import logging
from typing import Optional

import requests

from config.settings import (
    GEOAPIFY_API_KEY,
    GEOAPIFY_PLACES_URL,
    GEOAPIFY_GEOCODE_URL,
    GEOAPIFY_CATEGORY_MAP,
    GEOAPIFY_REQUEST_TIMEOUT,
)
from scraper.base_provider import DiscoveryProvider

logger = logging.getLogger(__name__)


class GeoapifyProvider(DiscoveryProvider):
    """
    Discovery provider using Geoapify's Places API.

    Free tier: 3,000 credits/day, no credit card required.
    Built on OSM data but may have different coverage/freshness.
    """

    @property
    def source_name(self) -> str:
        return "geoapify"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEOAPIFY_API_KEY
        if not self.api_key or self.api_key == "your_key_here":
            logger.warning("GEOAPIFY_API_KEY not configured -- Geoapify provider disabled")
            self._enabled = False
        else:
            self._enabled = True

    def search(
        self, country: str, city: str, category: str, count: int = 50
    ) -> list[dict]:
        """Search Geoapify for businesses matching category in city."""
        if not self._enabled:
            logger.info("Geoapify provider skipped (no API key)")
            return []

        # Step 1: Geocode city -> place_id
        place_id = self._geocode_city(city, country)
        if not place_id:
            logger.warning("Could not geocode %s, %s via Geoapify", city, country)
            return []

        # Step 2: Map category keyword to Geoapify category
        geo_category = self._map_category(category)
        if not geo_category:
            logger.warning("No Geoapify category mapping for %r, skipping", category)
            return []

        # Step 3: Search places
        results = self._search_places(geo_category, place_id, count, category)
        return self._tag_results(results)

    # -- Internal ----------------------------------------------------------

    def _geocode_city(self, city: str, country: str) -> Optional[str]:
        """Geocode a city name to a Geoapify place_id."""
        try:
            resp = requests.get(
                GEOAPIFY_GEOCODE_URL,
                params={
                    "text": f"{city}, {country}",
                    "type": "city",
                    "limit": 1,
                    "apiKey": self.api_key,
                },
                timeout=GEOAPIFY_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if features:
                pid = features[0]["properties"].get("place_id")
                logger.debug("Geocoded %s, %s -> place_id=%s", city, country, pid)
                return pid
            return None
        except Exception as exc:
            logger.error("Geoapify geocoding failed for %s, %s: %s", city, country, exc)
            return None

    def _map_category(self, category: str) -> Optional[str]:
        """Map a plain keyword to a Geoapify category code with fuzzy/stem fallback."""
        cat = category.lower().strip()
        
        # 1. Direct dictionary match
        if cat in GEOAPIFY_CATEGORY_MAP:
            return GEOAPIFY_CATEGORY_MAP[cat]
        
        # 2. Substring matching in keys
        for key, value in GEOAPIFY_CATEGORY_MAP.items():
            if key in cat or cat in key:
                return value

        # 3. Stem and synonym pattern fallbacks
        stem_rules = [
            (("cloth", "wear", "apparel", "garment", "boutique", "fashion", "dress", "textile"), "commercial.clothing"),
            (("shoe", "footwear", "sneaker", "boot"), "commercial.clothing"),
            (("dent", "tooth", "teeth", "orthodont"), "healthcare.dentist"),
            (("doc", "clinic", "medic", "health", "physician", "gp"), "healthcare.clinic_or_praxis"),
            (("pharma", "drug", "chemist", "apotheke"), "healthcare.pharmacy"),
            (("restaur", "diner", "eatery", "bistro", "food", "pizza", "burger"), "catering.restaurant"),
            (("cafe", "coffee", "bakery", "tea"), "catering.cafe"),
            (("market", "grocer", "supermarket", "mart"), "commercial.supermarket"),
            (("gym", "fit", "workout", "crossfit", "yoga"), "sport.fitness"),
            (("salon", "barber", "hair", "beauty", "spa"), "service.beauty"),
            (("repair", "mechanic", "auto", "garage", "car"), "service.vehicle.car_repair"),
            (("law", "attorney", "legal"), "office.lawyer"),
            (("account", "cpa", "tax", "audit"), "office.accountant"),
            (("hotel", "hostel", "motel", "resort"), "accommodation.hotel"),
        ]

        for stems, target_cat in stem_rules:
            if any(stem in cat for stem in stems):
                logger.debug("Stem rule matched %r -> %s", category, target_cat)
                return target_cat

        logger.debug("No Geoapify category mapping for %r", category)
        return None

    def _search_places(
        self, geo_category: str, place_id: str, count: int, original_category: str
    ) -> list[dict]:
        """Query the Geoapify Places API."""
        try:
            resp = requests.get(
                GEOAPIFY_PLACES_URL,
                params={
                    "categories": geo_category,
                    "filter": f"place:{place_id}",
                    "limit": min(count, 50),  # Geoapify max per request
                    "apiKey": self.api_key,
                },
                timeout=GEOAPIFY_REQUEST_TIMEOUT,
            )

            # Handle quota exhaustion gracefully
            if resp.status_code == 429:
                logger.warning("Geoapify quota exhausted (429). Returning empty results.")
                return []

            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            logger.info("Geoapify returned %d places for category %s", len(features), geo_category)

            return [
                self._parse_feature(f, original_category) for f in features
            ]

        except Exception as exc:
            logger.error("Geoapify places search failed: %s", exc)
            return []

    def _parse_feature(self, feature: dict, category: str) -> dict:
        """Transform a Geoapify feature into a standardized lead dict."""
        props = feature.get("properties", {})
        datasource = props.get("datasource", {})
        raw = datasource.get("raw", {})

        # Build address
        address_parts = [
            props.get("address_line1", ""),
            props.get("address_line2", ""),
        ]
        address = ", ".join(p for p in address_parts if p)

        # Standardize raw tags for the resolver (Fix #1)
        raw_tags = {}
        for key_variants, normalized_key in [
            (["contact:facebook", "facebook"], "contact:facebook"),
            (["contact:instagram", "instagram"], "contact:instagram"),
            (["contact:linkedin", "linkedin"], "contact:linkedin"),
            (["contact:twitter", "twitter"], "contact:twitter"),
        ]:
            for variant in key_variants:
                val = raw.get(variant) or props.get(variant)
                if val:
                    raw_tags[normalized_key] = val
                    break

        # Extract phone/website from multiple possible locations
        phone = (
            props.get("contact", {}).get("phone")
            or raw.get("phone")
            or raw.get("contact:phone")
        )
        website = (
            props.get("website")
            or raw.get("website")
            or raw.get("contact:website")
        )

        return {
            "business_name": props.get("name"),
            "category": category,
            "website": website,
            "phone": phone,
            "email": raw.get("email") or raw.get("contact:email"),
            "address": address or None,
            "city": props.get("city"),
            "country": props.get("country"),
            "source_url": None,
            "instagram": None,
            "facebook": None,
            "linkedin": None,
            "rating": None,
            "review_count": None,
            "status": "new",
            "_raw_tags": raw_tags,
        }
