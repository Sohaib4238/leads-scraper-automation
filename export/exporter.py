"""
Lead Exporter for Phase 3.

Exports qualified and analyzed leads to CSV and Excel (XLSX) formats using pandas.
Supports flexible multi-criteria filtering combined with AND logic:
- priority (HOT / WARM / COLD)
- service (matches within matched_services JSON array using canonical names)
- category / industry (matches business category with synonym/stem support)
- city, country (case-insensitive with ISO-2 / full name / multilingual alias support)
- min_score (minimum qualification score)
- has_email, has_phone, no_website (boolean flags)
- contactable (bool: ready for outreach vs needs_manual_lookup)
- discovery_sources (source tag match, e.g. 'osm' or 'geoapify')

Formats list fields (matched_services, discovery_sources) as clean comma-separated
strings rather than raw Python/JSON string literals.
Includes technical & performance signals (response_time_ms, page_size_kb).
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import select

from db.models import Lead
from db.session import get_session

logger = logging.getLogger(__name__)

# Standard country aliases for flexible 2-letter ISO vs full name filtering
COUNTRY_ALIASES: dict[str, set[str]] = {
    "pk": {"pk", "pakistan"},
    "de": {"de", "germany", "deutschland"},
    "gb": {"gb", "uk", "united kingdom", "great britain", "england", "scotland", "wales"},
    "us": {"us", "usa", "united states", "united states of america"},
    "ae": {"ae", "uae", "united arab emirates", "dubai", "abu dhabi"},
    "ca": {"ca", "canada"},
    "au": {"au", "australia"},
    "fr": {"fr", "france"},
}

# Multilingual and regional city aliases
CITY_ALIASES: dict[str, set[str]] = {
    "dubai": {"dubai", "دبي", "emirate of dubai"},
    "munich": {"munich", "münchen", "muenchen"},
    "berlin": {"berlin"},
    "london": {"london", "greater london"},
    "karachi": {"karachi", "karachi division", "کراچی"},
}

# Category synonyms / stem mappings
CATEGORY_SYNONYMS: dict[str, set[str]] = {
    "real estate": {"real estate", "estate_agent", "estate agent", "property", "realtor"},
    "estate_agent": {"real estate", "estate_agent", "estate agent", "property", "realtor"},
    "dentist": {"dentist", "dental", "dental clinic", "orthodontist"},
    "dental clinic": {"dentist", "dental", "dental clinic", "orthodontist"},
    "clothing store": {"clothing store", "clothes", "clothing", "apparel", "boutique", "fashion"},
    "cafe": {"cafe", "coffee", "coffee shop"},
    "restaurant": {"restaurant", "eatery", "diner"},
}


def _countries_match(filter_country: str, lead_country: Optional[str]) -> bool:
    """Check if filter country matches lead country via exact or alias matching."""
    if not lead_country:
        return False
    fc = filter_country.strip().lower()
    lc = lead_country.strip().lower()

    if fc == lc or fc in lc or lc in fc:
        return True

    for _, aliases in COUNTRY_ALIASES.items():
        if fc in aliases and lc in aliases:
            return True

    return False


def _cities_match(filter_city: str, lead_city: Optional[str]) -> bool:
    """Check if filter city matches lead city (handles 'Dubai' vs 'دبي', 'Munich' vs 'München')."""
    if not lead_city:
        return False
    f_city = filter_city.strip().lower()
    l_city = lead_city.strip().lower()

    if f_city == l_city or f_city in l_city or l_city in f_city:
        return True

    for _, aliases in CITY_ALIASES.items():
        if f_city in aliases and l_city in aliases:
            return True

    return False


def _categories_match(filter_cat: str, lead_cat: Optional[str]) -> bool:
    """Check if filter category/industry matches lead category with synonym support."""
    if not lead_cat:
        return False
    f_c = filter_cat.strip().lower()
    l_c = lead_cat.strip().lower()

    if f_c == l_c or f_c in l_c or l_c in f_c:
        return True

    for _, synonyms in CATEGORY_SYNONYMS.items():
        if f_c in synonyms and l_c in synonyms:
            return True

    return False


class LeadExporter:
    """Handles lead querying, multi-criteria filtering, and CSV/XLSX export."""

    @staticmethod
    def export_leads(
        output_path: str,
        format: str = "csv",
        priority: Optional[str] = None,
        service: Optional[str] = None,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        min_score: Optional[int] = None,
        has_email: Optional[bool] = None,
        has_phone: Optional[bool] = None,
        no_website: Optional[bool] = None,
        contactable: Optional[bool] = None,
        discovery_source: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Query leads from database with multi-filter AND logic and export to CSV/XLSX.
        Returns the filtered pandas DataFrame.
        """
        effective_category = category or industry
        logger.info(
            "Export initiated -> format=%s, priority=%s, service=%s, category=%s, city=%s, country=%s, min_score=%s, contactable=%s",
            format, priority, service, effective_category, city, country, min_score, contactable,
        )

        with get_session() as session:
            stmt = select(Lead)
            leads = session.scalars(stmt).all()

            filtered_rows = []
            for lead in leads:
                # 1. Priority filter
                if priority and (lead.priority or "").upper() != priority.upper():
                    continue

                # 2. Minimum Score filter
                if min_score is not None and (lead.score or 0) < min_score:
                    continue

                # 3. Category / Industry filter (case-insensitive with synonym matching)
                if effective_category and not _categories_match(effective_category, lead.category):
                    continue

                # 4. City filter (case-insensitive with alias match)
                if city and not _cities_match(city, lead.city):
                    continue

                # 5. Country filter (case-insensitive with alias match)
                if country and not _countries_match(country, lead.country):
                    continue

                # 6. has_email filter
                if has_email is True and not (lead.email and lead.email.strip()):
                    continue
                if has_email is False and (lead.email and lead.email.strip()):
                    continue

                # 7. has_phone filter
                if has_phone is True and not (lead.phone and lead.phone.strip()):
                    continue
                if has_phone is False and (lead.phone and lead.phone.strip()):
                    continue

                # 8. no_website filter
                if no_website is True and (lead.website and lead.website.strip()):
                    continue
                if no_website is False and not (lead.website and lead.website.strip()):
                    continue

                # 9. contactable filter
                if contactable is not None and bool(lead.contactable) != contactable:
                    continue

                # 10. Service filter (matches within matched_services JSON array)
                services_list = []
                if lead.matched_services:
                    try:
                        services_list = json.loads(lead.matched_services) if isinstance(lead.matched_services, str) else lead.matched_services
                    except Exception:
                        services_list = []
                if service:
                    service_match = any(service.lower() == s.lower() for s in services_list)
                    if not service_match:
                        continue

                # 11. Discovery source filter
                sources_list = []
                if lead.discovery_sources:
                    try:
                        sources_list = json.loads(lead.discovery_sources) if isinstance(lead.discovery_sources, str) else lead.discovery_sources
                    except Exception:
                        sources_list = []
                if discovery_source:
                    source_match = any(discovery_source.lower() in src.lower() for src in sources_list)
                    if not source_match:
                        continue

                # Clean representation for export
                services_str = ", ".join(services_list) if isinstance(services_list, list) else str(services_list or "")
                sources_str = ", ".join(sources_list) if isinstance(sources_list, list) else str(sources_list or "")

                row_dict = {
                    "id": lead.id,
                    "business_name": lead.business_name,
                    "category": lead.category,
                    "city": lead.city,
                    "country": lead.country,
                    "phone": lead.phone or "",
                    "email": lead.email or "",
                    "website": lead.website or "",
                    "address": lead.address or "",
                    "facebook": lead.facebook or "",
                    "instagram": lead.instagram or "",
                    "linkedin": lead.linkedin or "",
                    "rating": lead.rating,
                    "review_count": lead.review_count,
                    "score": lead.score or 0,
                    "priority": lead.priority or "COLD",
                    "lead_status": "actionable" if lead.contactable else "needs_manual_lookup",
                    "contactable": bool(lead.contactable),
                    "matched_services": services_str,
                    "response_time_ms": lead.response_time_ms if lead.response_time_ms is not None else "",
                    "page_size_kb": lead.page_size_kb if lead.page_size_kb is not None else "",
                    "reason": lead.reason or "",
                    "discovery_sources": sources_str,
                    "created_at": lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else "",
                }
                filtered_rows.append(row_dict)

        df = pd.DataFrame(filtered_rows)
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        fmt = format.lower().strip()
        is_excel = fmt in ("xlsx", "excel") or out_file.suffix.lower() == ".xlsx"

        try:
            if is_excel:
                df.to_excel(out_file, index=False, engine="openpyxl")
            else:
                df.to_csv(out_file, index=False, encoding="utf-8")
            logger.info("Exported %d leads to %s", len(df), out_file)
        except PermissionError:
            # If the user has the target file open in Excel/Viewer, fallback to timestamped file
            alt_path = out_file.with_name(f"{out_file.stem}_{int(time.time())}{out_file.suffix}")
            logger.warning("Target file %s is locked by another process. Writing to fallback: %s", out_file, alt_path)
            if is_excel:
                df.to_excel(alt_path, index=False, engine="openpyxl")
            else:
                df.to_csv(alt_path, index=False, encoding="utf-8")
            logger.info("Exported %d leads to fallback file: %s", len(df), alt_path)

        return df
