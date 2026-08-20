"""
OSM Overpass API discovery provider.

Uses dynamic city geocoding via Nominatim to get bounding boxes at runtime.
Includes rate limiting for Overpass & Nominatim (Fix #2), adaptive bbox retry
with clear logging (Fix #3), standardized _raw_tags format (Fix #1), and
robust category taxonomy mapping for multi-word queries.
"""

import logging
import time
import urllib.parse
from typing import Optional

import requests

from config.settings import (
    NOMINATIM_SEARCH_URL,
    NOMINATIM_USER_AGENT,
    NOMINATIM_REQUEST_DELAY,
    OSM_OVERPASS_MIRRORS,
    OSM_QUERY_TIMEOUT,
    OSM_REQUEST_TIMEOUT,
    OSM_REQUEST_DELAY,
)
from scraper.base_provider import DiscoveryProvider

logger = logging.getLogger(__name__)


class OSMProvider(DiscoveryProvider):
    """
    Discovery provider using OpenStreetMap's Overpass API.

    Searches for businesses by category within a city's bounding box
    retrieved dynamically via Nominatim.
    Falls back to mirror servers if the primary fails.
    """

    @property
    def source_name(self) -> str:
        return "osm"

    def __init__(self):
        self._last_overpass_time: float = 0.0
        self._last_nominatim_time: float = 0.0
        self._bbox_retries: int = 0

    @property
    def bbox_retries(self) -> int:
        """Number of bbox-shrink retries that occurred during the last search."""
        return self._bbox_retries

    def search(
        self, country: str, city: str, category: str, count: int = 50
    ) -> list[dict]:
        """Search Overpass for businesses matching category in city."""
        self._bbox_retries = 0

        bbox = self._geocode_city_bbox(city, country)
        if not bbox:
            logger.error(
                "OSM discovery failed: No bounding box found for city '%s', country '%s' via Nominatim",
                city, country,
            )
            raise ValueError(f"No bounding box found for '{city}, {country}' via OSM/Nominatim geocoder")

        tag_keys = self._get_tag_keys(category)
        results = self._query_with_retry(category, tag_keys, bbox, count)

        return self._tag_results(results)

    # -- Internal ----------------------------------------------------------

    def _geocode_city_bbox(self, city: str, country: str) -> Optional[str]:
        """
        Dynamically fetch the bounding box for a city using Nominatim.
        Format returned: 'south,west,north,east' for Overpass QL.
        """
        self._respect_nominatim_rate_limit()

        params = {
            "city": city,
            "country": country,
            "format": "json",
            "limit": 1,
        }
        headers = {
            "User-Agent": NOMINATIM_USER_AGENT,
        }

        try:
            resp = requests.get(
                NOMINATIM_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                params_fallback = {
                    "q": f"{city}, {country}",
                    "format": "json",
                    "limit": 1,
                }
                resp_fb = requests.get(
                    NOMINATIM_SEARCH_URL,
                    params=params_fallback,
                    headers=headers,
                    timeout=20,
                )
                resp_fb.raise_for_status()
                data = resp_fb.json()

            if data:
                raw_bbox = data[0].get("boundingbox")
                if raw_bbox and len(raw_bbox) == 4:
                    south, north, west, east = raw_bbox
                    bbox_str = f"{south},{west},{north},{east}"
                    logger.info(
                        "Nominatim geocoded '%s, %s' to bbox: %s",
                        city, country, bbox_str,
                    )
                    return bbox_str

            return None
        except Exception as exc:
            logger.error("Nominatim geocoding error for '%s, %s': %s", city, country, exc)
            return None

    def _respect_nominatim_rate_limit(self):
        """Enforce maximum 1 req/sec policy for Nominatim."""
        elapsed = time.time() - self._last_nominatim_time
        if elapsed < NOMINATIM_REQUEST_DELAY:
            wait = NOMINATIM_REQUEST_DELAY - elapsed
            time.sleep(wait)
        self._last_nominatim_time = time.time()

    def _get_tag_keys(self, category: str) -> list[str]:
        """Map a category keyword to OSM tag keys to search across."""
        cat = category.lower().strip()
        # Real Estate & Professional Offices
        if any(k in cat for k in ("real estate", "estate agent", "property", "realtor", "law", "attorney", "legal", "account", "tax", "audit")):
            return ["office", "shop", "amenity"]
        # Healthcare categories
        if any(k in cat for k in ("dent", "doctor", "clinic", "hospital", "pharma", "medic", "physician", "health")):
            return ["amenity", "healthcare"]
        # Food & Dining
        if any(k in cat for k in ("restaurant", "cafe", "coffee", "food", "bakery", "burger", "pizza", "bar", "pub", "diner", "eatery")):
            return ["amenity"]
        # Shopping & Retail
        if any(k in cat for k in ("cloth", "wear", "apparel", "garment", "boutique", "fashion", "shoe", "footwear", "shop", "store", "supermarket", "grocer", "mart", "mall", "market")):
            return ["shop"]
        # Services & Craft
        if any(k in cat for k in ("salon", "barber", "hair", "beauty", "spa", "repair", "mechanic", "auto", "garage", "laundry", "clean")):
            return ["shop", "craft", "amenity"]
        # Sports & Fitness
        if any(k in cat for k in ("gym", "fit", "workout", "crossfit", "yoga", "sport")):
            return ["leisure", "sport", "amenity"]
        # Accommodation & Tourism
        if any(k in cat for k in ("hotel", "hostel", "motel", "resort", "lodging")):
            return ["tourism"]
        # Default: search broadly
        return ["amenity", "shop", "healthcare", "office", "craft", "leisure"]

    def _map_category_to_tag_value(self, category: str) -> str:
        """Map user keywords/synonyms to canonical OSM tag values."""
        cat = category.lower().strip()
        
        mapping = {
            # Real estate
            "real estate": "estate_agent", "estate agent": "estate_agent",
            "property": "estate_agent", "realtor": "estate_agent",
            "real estate agency": "estate_agent",

            # Clothing / Fashion
            "clothing store": "clothes", "clothing": "clothes", "clothes": "clothes",
            "apparel": "clothes", "boutique": "clothes", "fashion": "clothes",
            "garments": "clothes", "dress shop": "clothes",
            "shoe store": "shoes", "shoe shop": "shoes", "shoes": "shoes", "footwear": "shoes",
            
            # Healthcare
            "dental clinic": "dentist", "dental": "dentist", "dentist": "dentist", "dental care": "dentist",
            "doctor": "doctors", "medical clinic": "clinic", "clinic": "clinic", "hospital": "hospital",
            "pharmacy": "pharmacy", "chemist": "pharmacy", "drugstore": "pharmacy",
            
            # Food & Drink
            "restaurant": "restaurant", "cafe": "cafe", "coffee shop": "cafe", "coffee": "cafe",
            "fast food": "fast_food", "bakery": "bakery", "bar": "bar", "pub": "pub",
            
            # Retail & Groceries
            "supermarket": "supermarket", "grocery": "supermarket", "grocery store": "supermarket",
            "convenience store": "convenience", "department store": "department_store",
            
            # Personal Care & Services
            "hair salon": "hairdresser", "salon": "hairdresser", "barber": "hairdresser", "hairdresser": "hairdresser",
            "beauty": "beauty", "beauty salon": "beauty", "spa": "spa",
            "gym": "fitness_centre", "fitness": "fitness_centre", "fitness center": "fitness_centre",
            "car repair": "car_repair", "auto repair": "car_repair", "mechanic": "car_repair", "garage": "car_repair",
            
            # Professional
            "lawyer": "lawyer", "attorney": "lawyer", "law firm": "lawyer",
            "accountant": "accountant", "accounting": "accountant",
            "hotel": "hotel", "hostel": "hostel", "school": "school",
        }
        if cat in mapping:
            return mapping[cat]

        # Stem / keyword fallbacks
        if "estate" in cat or "realt" in cat or "propert" in cat:
            return "estate_agent"
        if "cloth" in cat or "apparel" in cat or "fashion" in cat or "boutique" in cat:
            return "clothes"
        if "shoe" in cat or "footwear" in cat:
            return "shoes"
        if "dent" in cat or "tooth" in cat or "teeth" in cat:
            return "dentist"
        if "coffee" in cat or "cafe" in cat:
            return "cafe"
        if "restaur" in cat or "diner" in cat or "eatery" in cat:
            return "restaurant"
        if "grocer" in cat or "supermarket" in cat or "market" in cat:
            return "supermarket"
        if "gym" in cat or "fitness" in cat:
            return "fitness_centre"
        if "salon" in cat or "barber" in cat or "hair" in cat:
            return "hairdresser"
        if "repair" in cat or "mechanic" in cat or "auto" in cat:
            return "car_repair"

        return cat

    def _query_with_retry(
        self, category: str, tag_keys: list[str], bbox: str, count: int
    ) -> list[dict]:
        """Query Overpass with adaptive bbox retry."""
        tag_value = self._map_category_to_tag_value(category)

        # Attempt 1: full bbox
        results = self._execute_query(tag_value, tag_keys, bbox, count, original_category=category)
        if results is not None:
            return results

        # Attempt 2: shrink bbox to 50%
        shrunk_bbox = self._shrink_bbox(bbox, factor=0.5)
        self._bbox_retries += 1
        logger.warning(
            "OSM query timed out for %r with full bbox %s. "
            "RETRYING with 50%% smaller bbox %s.",
            category, bbox, shrunk_bbox,
        )
        results = self._execute_query(tag_value, tag_keys, shrunk_bbox, count, original_category=category)
        if results is not None:
            return results

        logger.error("OSM query failed on both full and shrunk bbox for %r", category)
        return []

    def _execute_query(
        self, tag_value: str, tag_keys: list[str], bbox: str, count: int, original_category: str
    ) -> Optional[list[dict]]:
        """Execute a single Overpass query across all tag keys."""
        filters = "".join(
            f'node["{key}"="{tag_value}"]({bbox});'
            for key in tag_keys
        )
        query = f"[out:json][timeout:{OSM_QUERY_TIMEOUT}];({filters});out {count};"

        self._respect_overpass_rate_limit()

        for mirror_url in OSM_OVERPASS_MIRRORS:
            try:
                url = f"{mirror_url}?data={urllib.parse.quote(query)}"
                logger.debug("OSM GET %s", mirror_url)

                resp = requests.get(
                    url,
                    timeout=OSM_REQUEST_TIMEOUT,
                    headers={"User-Agent": "LeadScraper/1.0"},
                )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 10))
                    logger.warning("OSM mirror %s returned 429. Backing off %ds.", mirror_url, retry_after)
                    time.sleep(retry_after)
                    continue

                if resp.status_code == 406:
                    continue

                resp.raise_for_status()
                data = resp.json()
                elements = data.get("elements", [])
                logger.info("OSM query returned %d elements from %s", len(elements), mirror_url)
                return [self._parse_element(el, original_category) for el in elements]

            except requests.exceptions.Timeout:
                logger.warning("OSM mirror %s timed out after %ds", mirror_url, OSM_REQUEST_TIMEOUT)
                continue
            except Exception as exc:
                logger.error("OSM mirror %s error: %s", mirror_url, exc)
                continue

        return None

    def _respect_overpass_rate_limit(self):
        """Enforce minimum delay between Overpass requests."""
        elapsed = time.time() - self._last_overpass_time
        if elapsed < OSM_REQUEST_DELAY:
            wait = OSM_REQUEST_DELAY - elapsed
            time.sleep(wait)
        self._last_overpass_time = time.time()

    def _parse_element(self, element: dict, category: str) -> dict:
        """Transform an Overpass element into a standardized lead dict with original user category."""
        tags = element.get("tags", {})

        address_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:suburb", ""),
        ]
        address = ", ".join(p for p in address_parts if p) or tags.get("addr:full", "")

        raw_tags = {}
        for osm_key, normalized_key in [
            ("contact:facebook", "contact:facebook"),
            ("facebook", "contact:facebook"),
            ("contact:instagram", "contact:instagram"),
            ("instagram", "contact:instagram"),
            ("contact:linkedin", "contact:linkedin"),
            ("linkedin", "contact:linkedin"),
            ("contact:twitter", "contact:twitter"),
            ("twitter", "contact:twitter"),
        ]:
            if tags.get(osm_key):
                raw_tags[normalized_key] = tags[osm_key]

        return {
            "business_name": tags.get("name"),
            "category": category,
            "website": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "email": tags.get("email") or tags.get("contact:email"),
            "address": address or None,
            "city": tags.get("addr:city"),
            "country": tags.get("addr:country"),
            "source_url": f"https://www.openstreetmap.org/node/{element.get('id', '')}",
            "instagram": None,
            "facebook": None,
            "linkedin": None,
            "rating": None,
            "review_count": None,
            "status": "new",
            "_raw_tags": raw_tags,
        }

    @staticmethod
    def _shrink_bbox(bbox: str, factor: float = 0.5) -> str:
        """Shrink a bbox towards its center by the given factor."""
        s, w, n, e = [float(x) for x in bbox.split(",")]
        lat_center = (s + n) / 2
        lon_center = (w + e) / 2
        lat_half = (n - s) / 2 * factor
        lon_half = (e - w) / 2 * factor
        return f"{lat_center-lat_half:.4f},{lon_center-lon_half:.4f},{lat_center+lat_half:.4f},{lon_center+lon_half:.4f}"
