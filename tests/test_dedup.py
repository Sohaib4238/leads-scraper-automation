"""
Tests for the deduplication engine.

Uses an in-memory SQLite database for complete test isolation.
Covers:
  1. Exact domain match (different URLs, same domain)
  2. Phone match with formatting differences (+92 vs 0092 vs 03xx)
  3. Fuzzy name + address match (minor spelling differences)
  4. Non-duplicate verification (genuinely different businesses)
  5. Edge case: one lead has phone only, other has website only
  6. Hash collision prevention: same name in different cities
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import Base, Lead
from db.crud import create_lead, get_lead_by_dedup_hash
from scraper.dedup import DeduplicationEngine


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for test isolation."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def session(engine):
    """Yield a session bound to the in-memory DB; rolls back after each test."""
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture
def dedup():
    """Fresh DeduplicationEngine instance."""
    return DeduplicationEngine()


# ── Helper ─────────────────────────────────────────────────────────────


def _make_lead(
    name: str = "Test Business",
    website: str = None,
    phone: str = None,
    email: str = None,
    address: str = "123 Main St",
    city: str = "Karachi",
    country: str = "PK",
    **kwargs,
) -> dict:
    """Build a lead_data dict with sensible defaults."""
    return {
        "business_name": name,
        "category": "test",
        "website": website,
        "phone": phone,
        "email": email,
        "address": address,
        "city": city,
        "country": country,
        "source_url": "https://maps.google.com/test",
        "instagram": None,
        "facebook": None,
        "linkedin": None,
        "rating": 4.0,
        "review_count": 10,
        "status": "new",
        **kwargs,
    }


def _insert_lead(session, dedup, lead_data, country_code="PK"):
    """Normalize and insert a lead into the test DB."""
    normalized = dedup.normalize_lead_for_storage(lead_data, country_code)
    return create_lead(session, normalized)


# ── Test: Domain matching ──────────────────────────────────────────────


class TestDomainDedup:
    """Leads with the same domain (after normalization) should be detected as duplicates."""

    def test_same_domain_different_urls(self, session, dedup):
        """https://www.example.com/about and http://example.com → same domain → duplicate."""
        lead1 = _make_lead(name="Biz A", website="https://www.example.com/about")
        _insert_lead(session, dedup, lead1)
        session.flush()

        lead2 = _make_lead(name="Biz B", website="http://example.com")
        assert dedup.is_duplicate(session, lead2, "PK") is True

    def test_different_domains_not_duplicate(self, session, dedup):
        """Different domains should NOT match."""
        lead1 = _make_lead(name="Alpha Dental Surgery", website="https://clinicone.com", address="10 Ocean Blvd", city="Islamabad")
        _insert_lead(session, dedup, lead1)
        session.flush()

        lead2 = _make_lead(name="Zenith Eye Hospital", website="https://clinictwo.com", address="777 Mountain Rd", city="Lahore")
        assert dedup.is_duplicate(session, lead2, "PK") is False

    def test_www_stripping(self, session, dedup):
        """www.example.com and example.com should be treated as the same domain."""
        lead1 = _make_lead(name="Biz A", website="http://www.mysite.pk")
        _insert_lead(session, dedup, lead1)
        session.flush()

        lead2 = _make_lead(name="Biz A Copy", website="https://mysite.pk/contact")
        assert dedup.is_duplicate(session, lead2, "PK") is True


# ── Test: Phone matching ──────────────────────────────────────────────


class TestPhoneDedup:
    """Leads with the same phone (after E.164 normalization) should be duplicates."""

    def test_international_vs_local_format(self, session, dedup):
        """+92-300-1234567 and 03001234567 → same number → duplicate.
        phonenumbers needs region hint "PK" to parse the local format correctly.
        """
        lead1 = _make_lead(name="Clinic A", phone="+92-300-1234567")
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(name="Clinic B", phone="03001234567")
        assert dedup.is_duplicate(session, lead2, "PK") is True

    def test_double_zero_prefix(self, session, dedup):
        """0092 300 123 4567 and +923001234567 → same number."""
        lead1 = _make_lead(name="Clinic X", phone="+923001234567")
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(name="Clinic Y", phone="0092 300 123 4567")
        assert dedup.is_duplicate(session, lead2, "PK") is True

    def test_different_phone_numbers(self, session, dedup):
        """Completely different numbers should NOT match."""
        lead1 = _make_lead(name="Rawalpindi Auto Parts", phone="+923001234567", address="5 Factory Lane", city="Rawalpindi")
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(name="Lahore Book Depot", phone="+923219876543", address="88 University Road", city="Lahore")
        assert dedup.is_duplicate(session, lead2, "PK") is False


# ── Test: Fuzzy name + address matching ────────────────────────────────


class TestFuzzyDedup:
    """Minor spelling differences in name+address should still match (score ≥ 90)."""

    def test_minor_name_difference(self, session, dedup):
        """
        "Dr. Ahmed Dental Clinic" vs "Dr Ahmed Dental Clinic"
        at the same address → should be a fuzzy match (token_sort_ratio ≥ 90).
        The names differ only by a period — well above the 90 threshold.
        """
        lead1 = _make_lead(
            name="Dr. Ahmed Dental Clinic",
            address="123 Main Street, Block 5",
            city="Karachi",
        )
        _insert_lead(session, dedup, lead1)
        session.flush()

        lead2 = _make_lead(
            name="Dr Ahmed Dental Clinic",
            address="123 Main Street Block 5",
            city="Karachi",
        )
        assert dedup.is_duplicate(session, lead2, "PK") is True

    def test_very_different_names_not_fuzzy_match(self, session, dedup):
        """Completely different businesses in the same city should NOT match."""
        lead1 = _make_lead(
            name="Dr. Ahmed Dental Clinic",
            address="123 Main St",
            city="Karachi",
        )
        _insert_lead(session, dedup, lead1)
        session.flush()

        lead2 = _make_lead(
            name="Khan Auto Repair Shop",
            address="456 Industrial Rd",
            city="Karachi",
        )
        assert dedup.is_duplicate(session, lead2, "PK") is False


# ── Test: Edge cases ──────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases that exercise the dedup_hash fallback logic."""

    def test_phone_only_vs_website_only_different_names(self, session, dedup):
        """
        Lead 1 has phone but no website.
        Lead 2 has website but no phone.
        Different names → should NOT be a duplicate.
        """
        lead1 = _make_lead(
            name="Biz Alpha",
            phone="+923001234567",
            website=None,
            address="100 Some Road",
            city="Lahore",
        )
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(
            name="Biz Beta",
            phone=None,
            website="https://bizbeta.pk",
            address="200 Other Road",
            city="Lahore",
        )
        assert dedup.is_duplicate(session, lead2, "PK") is False

    def test_same_name_different_cities_not_duplicate(self, session, dedup):
        """
        Two businesses named "Al-Karam General Store" in different cities.
        Both have no website and no phone.
        Should NOT collide because city is included in the hash fallback.
        """
        lead1 = _make_lead(
            name="Al-Karam General Store",
            phone=None,
            website=None,
            address="Main Bazaar",
            city="Karachi",
        )
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(
            name="Al-Karam General Store",
            phone=None,
            website=None,
            address="Main Bazaar",
            city="Lahore",
        )
        # Different city → different hash → NOT a duplicate
        assert dedup.is_duplicate(session, lead2, "PK") is False

    def test_same_name_same_city_no_contact_is_duplicate(self, session, dedup):
        """
        Same name + same city + same address + no phone + no website → duplicate.
        This is the hash fallback with city included.
        """
        lead1 = _make_lead(
            name="Al-Karam General Store",
            phone=None,
            website=None,
            address="Main Bazaar",
            city="Karachi",
        )
        _insert_lead(session, dedup, lead1, "PK")
        session.flush()

        lead2 = _make_lead(
            name="Al-Karam General Store",
            phone=None,
            website=None,
            address="Main Bazaar",
            city="Karachi",
        )
        assert dedup.is_duplicate(session, lead2, "PK") is True


# ── Test: Normalization helpers directly ──────────────────────────────


class TestNormalizationHelpers:
    """Unit tests for the static normalization methods."""

    def test_normalize_domain_strips_www_and_path(self, dedup):
        assert dedup.normalize_domain("https://www.example.com/about") == "example.com"

    def test_normalize_domain_lowercases(self, dedup):
        assert dedup.normalize_domain("HTTP://EXAMPLE.COM") == "example.com"

    def test_normalize_domain_none_returns_none(self, dedup):
        assert dedup.normalize_domain(None) is None
        assert dedup.normalize_domain("") is None

    def test_normalize_domain_no_scheme(self, dedup):
        assert dedup.normalize_domain("example.com") == "example.com"

    def test_normalize_phone_pk_international(self, dedup):
        result = dedup.normalize_phone("+92-300-1234567", "PK")
        assert result == "+923001234567"

    def test_normalize_phone_pk_local(self, dedup):
        result = dedup.normalize_phone("03001234567", "PK")
        assert result == "+923001234567"

    def test_normalize_phone_none_returns_none(self, dedup):
        assert dedup.normalize_phone(None, "PK") is None
        assert dedup.normalize_phone("", "PK") is None
