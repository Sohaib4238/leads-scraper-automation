"""
Discovery merger -- runs multiple providers and merges results via dedup.

Cross-provider dedup works on name+address alone (the common case when
phone/domain are both missing). When merging duplicates, the best non-None
value for each field is kept.
"""

import logging
from typing import Optional

from rapidfuzz import fuzz

from config.settings import FUZZY_MATCH_THRESHOLD
from scraper.dedup import DeduplicationEngine

logger = logging.getLogger(__name__)


def merge_discovery_results(
    provider_results: dict[str, list[dict]],
    country_code: str = "US",
) -> list[dict]:
    """
    Merge results from multiple discovery providers into a deduplicated list.

    For leads found by multiple providers, merges discovery_sources and fills
    gaps (e.g., OSM has phone, Geoapify has website -> merged lead has both).

    Args:
        provider_results: {"osm": [lead_dicts], "geoapify": [lead_dicts]}
        country_code: ISO alpha-2 country code for phone normalization.

    Returns:
        List of merged, deduplicated lead dicts.
    """
    merged: list[dict] = []

    for source_name, leads in provider_results.items():
        for lead in leads:
            lead["_source"] = source_name

            # Try to find a matching lead already in merged
            match_idx = _find_match(lead, merged, country_code)

            if match_idx is not None:
                # Merge into existing
                merged[match_idx] = _merge_leads(merged[match_idx], lead)
                logger.debug(
                    "Merged %r from %s into existing lead from %s",
                    lead.get("business_name"),
                    source_name,
                    merged[match_idx].get("discovery_sources"),
                )
            else:
                # New unique lead
                lead["discovery_sources"] = [source_name]
                merged.append(lead)

    logger.info(
        "Discovery merge: %d total inputs -> %d unique leads",
        sum(len(v) for v in provider_results.values()),
        len(merged),
    )
    return merged


def _cities_match(c1: str, c2: str) -> bool:
    """Check if two city strings refer to the same city (e.g. London vs Greater London)."""
    if not c1 or not c2:
        return True  # If one is missing, allow name+address fuzzy match
    c1, c2 = c1.lower().strip(), c2.lower().strip()
    return c1 == c2 or c1 in c2 or c2 in c1


def _find_match(lead: dict, existing: list[dict], country_code: str = "US") -> Optional[int]:
    """
    Find an existing lead that matches this one.

    Checks in order:
    1. Normalized domain match
    2. Normalized phone match (E.164)
    3. Fuzzy name+address match within matching city
    """
    lead_website = lead.get("website")
    lead_domain = DeduplicationEngine.normalize_domain(lead_website)

    lead_phone = lead.get("phone")
    lead_phone_norm = DeduplicationEngine.normalize_phone(lead_phone, country_code)

    lead_name = (lead.get("business_name") or "").strip().lower()
    lead_address = (lead.get("address") or "").strip().lower()
    lead_city = (lead.get("city") or "").strip().lower()

    for i, ex in enumerate(existing):
        # 1. Domain match
        if lead_domain:
            ex_domain = DeduplicationEngine.normalize_domain(ex.get("website"))
            if ex_domain and lead_domain == ex_domain:
                return i

        # 2. Phone match (E.164 normalized)
        if lead_phone_norm:
            ex_phone_norm = DeduplicationEngine.normalize_phone(ex.get("phone"), country_code)
            if ex_phone_norm and lead_phone_norm == ex_phone_norm:
                return i

        # 3. Fuzzy name+address
        ex_city = (ex.get("city") or "").strip().lower()
        if _cities_match(lead_city, ex_city) and lead_name:
            ex_name = (ex.get("business_name") or "").strip().lower()
            ex_address = (ex.get("address") or "").strip().lower()
            candidate = f"{lead_name} {lead_address}".strip()
            existing_str = f"{ex_name} {ex_address}".strip()
            score = fuzz.token_sort_ratio(candidate, existing_str)
            if score >= FUZZY_MATCH_THRESHOLD:
                return i

    return None


def _merge_leads(existing: dict, new: dict) -> dict:
    """
    Merge a new lead into an existing one, preferring non-None values.

    Combines discovery_sources lists and fills gaps from whichever provider
    has the data.
    """
    merged = dict(existing)

    # Combine discovery sources
    sources = set(existing.get("discovery_sources") or [])
    sources.add(new.get("_source", "unknown"))
    merged["discovery_sources"] = sorted(sources)

    # Fill gaps: prefer non-None values from either source
    fill_fields = [
        "website", "phone", "email", "address", "city", "country",
        "rating", "review_count", "source_url",
    ]
    for field in fill_fields:
        if not merged.get(field) and new.get(field):
            merged[field] = new[field]

    # Merge raw tags (union of both)
    existing_tags = existing.get("_raw_tags", {})
    new_tags = new.get("_raw_tags", {})
    merged_tags = {**existing_tags, **new_tags}
    merged["_raw_tags"] = merged_tags

    return merged
