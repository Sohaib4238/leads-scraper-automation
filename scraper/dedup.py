"""
Deduplication engine for leads.

Checks for duplicates across 4 dimensions (short-circuits on first match):
  1. Normalized website domain
  2. Normalized phone number (via phonenumbers library with region hint)
  3. Email (case-insensitive)
  4. Fuzzy name + address match (rapidfuzz, threshold ≥ 90)

The dedup_hash stored on each Lead is SHA256(normalized_domain|normalized_phone|lowercase_name|city_fallback)
for fast exact lookups. Fuzzy matching is a slower secondary pass.
"""

import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import phonenumbers
from rapidfuzz import fuzz

from config.settings import FUZZY_MATCH_THRESHOLD
from db.crud import (
    get_lead_by_dedup_hash,
    get_lead_by_phone,
    get_lead_by_website_domain,
    get_lead_by_email,
    get_leads_by_city,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """
    Determines whether a lead is a duplicate before insertion.

    Usage:
        engine = DeduplicationEngine()
        is_dup = engine.is_duplicate(session, lead_data, country_code="PK")
        if not is_dup:
            lead_data["dedup_hash"] = engine.compute_dedup_hash(lead_data, country_code="PK")
            create_lead(session, lead_data)
    """

    # ── Public API ─────────────────────────────────────────────────

    def is_duplicate(
        self, session: Session, lead_data: dict, country_code: str = "US"
    ) -> bool:
        """
        Check if lead_data matches an existing lead in the database.

        Checks are run in order of speed (fast exact lookups first,
        expensive fuzzy match last). Short-circuits on first match.

        Args:
            session: Active SQLAlchemy session.
            lead_data: Dict of lead fields (as returned by PlacesClient._parse_place).
            country_code: ISO 3166-1 alpha-2 code (e.g. "PK") — used as region hint
                          for phonenumbers.parse() when the number is in local format.
        """
        # 1. Fast path: dedup hash
        dedup_hash = self.compute_dedup_hash(lead_data, country_code)
        existing = get_lead_by_dedup_hash(session, dedup_hash)
        if existing:
            logger.debug(
                "Duplicate (hash match): %r matches existing lead #%d",
                lead_data.get("business_name"), existing.id,
            )
            return True

        # 2. Domain match
        domain = self.normalize_domain(lead_data.get("website"))
        if domain:
            existing = get_lead_by_website_domain(session, domain)
            if existing:
                logger.debug(
                    "Duplicate (domain match): %r domain=%r matches lead #%d",
                    lead_data.get("business_name"), domain, existing.id,
                )
                return True

        # 3. Phone match
        normalized_phone = self.normalize_phone(lead_data.get("phone"), country_code)
        if normalized_phone:
            existing = get_lead_by_phone(session, normalized_phone)
            if existing:
                logger.debug(
                    "Duplicate (phone match): %r phone=%r matches lead #%d",
                    lead_data.get("business_name"), normalized_phone, existing.id,
                )
                return True

        # 4. Email match
        email = (lead_data.get("email") or "").strip().lower()
        if email:
            existing = get_lead_by_email(session, email)
            if existing:
                logger.debug(
                    "Duplicate (email match): %r email=%r matches lead #%d",
                    lead_data.get("business_name"), email, existing.id,
                )
                return True

        # 5. Fuzzy name + address (slowest — only within same city)
        city = lead_data.get("city", "")
        name = lead_data.get("business_name", "")
        address = lead_data.get("address", "")
        if name and city:
            if self._fuzzy_match_exists(session, name, address, city):
                logger.debug(
                    "Duplicate (fuzzy match): %r in %r",
                    name, city,
                )
                return True

        return False

    def compute_dedup_hash(self, lead_data: dict, country_code: str = "US") -> str:
        """
        Compute a deterministic SHA256 hash for fast exact-match dedup.

        Hash components: normalized_domain | normalized_phone | lowercase_name
        When both domain and phone are empty (common for small local businesses),
        the city is included to prevent collisions between same-named businesses
        in different cities (e.g. "Al-Karam General Store" in Karachi vs Lahore).
        """
        domain = self.normalize_domain(lead_data.get("website")) or ""
        phone = self.normalize_phone(lead_data.get("phone"), country_code) or ""
        name = (lead_data.get("business_name") or "").strip().lower()

        # Include city in the hash when both domain and phone are absent
        # to avoid collision between same-named businesses in different cities
        if not domain and not phone:
            city = (lead_data.get("city") or "").strip().lower()
            raw = f"{domain}|{phone}|{name}|{city}"
        else:
            raw = f"{domain}|{phone}|{name}"

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── Normalization helpers ──────────────────────────────────────

    @staticmethod
    def normalize_domain(url: Optional[str]) -> Optional[str]:
        """
        Extract and normalize domain from a URL.

        Examples:
            "https://www.example.com/about"  →  "example.com"
            "http://Example.COM"             →  "example.com"
            ""  /  None                      →  None
        """
        if not url or not url.strip():
            return None

        url = url.strip()
        # Ensure it has a scheme so urlparse works (case-insensitive check)
        if not url.lower().startswith(("http://", "https://")):
            url = "http://" + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
            domain = domain.lower().strip()
            # Strip www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            # Strip port
            domain = domain.split(":")[0]
            return domain if domain else None
        except Exception:
            return None

    @staticmethod
    def normalize_phone(
        phone: Optional[str], country_code: str = "US"
    ) -> Optional[str]:
        """
        Normalize a phone number to E.164 format using the phonenumbers library.

        The country_code param is the ISO 3166-1 alpha-2 code (e.g. "PK", "US")
        used as a region hint for parsing local-format numbers like "03001234567".

        Examples (with country_code="PK"):
            "+92-300-1234567"   →  "+923001234567"
            "03001234567"       →  "+923001234567"
            "0092 300 123 4567" →  "+923001234567"

        Returns None if the number can't be parsed or is clearly invalid.
        """
        if not phone or not phone.strip():
            return None

        raw = phone.strip()

        try:
            # phonenumbers.parse() needs the region hint for local-format numbers
            parsed = phonenumbers.parse(raw, country_code.upper())
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
            else:
                # Number parsed but isn't valid — try as-is with digit stripping
                logger.debug("Phone %r parsed but not valid for region %s", raw, country_code)
                digits = re.sub(r"\D", "", raw)
                return f"+{digits}" if digits else None
        except phonenumbers.NumberParseException:
            # Can't parse — fall back to digit stripping for storage consistency
            logger.debug("Could not parse phone %r with region %s", raw, country_code)
            digits = re.sub(r"\D", "", raw)
            return f"+{digits}" if digits else None

    # ── Fuzzy matching ─────────────────────────────────────────────

    def _fuzzy_match_exists(
        self,
        session: Session,
        name: str,
        address: str,
        city: str,
    ) -> bool:
        """
        Check if a lead with a similar name+address already exists in the same city.

        Uses rapidfuzz token_sort_ratio for order-insensitive comparison.
        Threshold is configured in settings (default 90).
        """
        existing_leads = get_leads_by_city(session, city)
        candidate = f"{name} {address}".strip().lower()

        for lead in existing_leads:
            existing_str = f"{lead.business_name or ''} {lead.address or ''}".strip().lower()
            score = fuzz.token_sort_ratio(candidate, existing_str)
            if score >= FUZZY_MATCH_THRESHOLD:
                logger.debug(
                    "Fuzzy match (score=%.1f): %r ≈ %r",
                    score, candidate, existing_str,
                )
                return True

        return False

    # ── Pre-insertion normalization ─────────────────────────────────

    def normalize_lead_for_storage(
        self, lead_data: dict, country_code: str = "US"
    ) -> dict:
        """
        Normalize phone and email fields before inserting into the database.
        This ensures consistent storage format for future dedup lookups.

        Returns a new dict (does not mutate the original).
        """
        data = dict(lead_data)

        # Normalize phone to E.164
        raw_phone = data.get("phone")
        if raw_phone:
            data["phone"] = self.normalize_phone(raw_phone, country_code) or raw_phone

        # Normalize email to lowercase
        raw_email = data.get("email")
        if raw_email:
            data["email"] = raw_email.strip().lower()

        # Compute dedup hash
        data["dedup_hash"] = self.compute_dedup_hash(data, country_code)

        return data
