"""
Tests for pipeline/coverage_reporter.py (Fix #4)

Verifies:
- WARNING fires below the 15% threshold
- WARNING does NOT fire above it
- Bbox-retry warning is included when retries > 0
- Coverage stats are computed correctly
"""

import logging
import pytest
from pipeline.coverage_reporter import compute_coverage_report, CoverageReport


def _make_leads(total: int, with_phone: int = 0, with_website: int = 0, with_social: int = 0) -> list[dict]:
    """Helper: create a list of minimal lead dicts with controlled fill rates."""
    leads = []
    for i in range(total):
        lead = {
            "business_name": f"Business {i}",
            "phone": f"+9230012345{i:02d}" if i < with_phone else None,
            "website": f"https://biz{i}.pk" if i < with_website else None,
            "email": None,
            "facebook": f"https://fb.com/biz{i}" if i < with_social else None,
            "instagram": None,
            "linkedin": None,
        }
        leads.append(lead)
    return leads


class TestCoverageComputation:
    """Verify fill rates and zero_web_presence counts are correct."""

    def test_all_filled(self):
        """100% fill rates."""
        leads = _make_leads(10, with_phone=10, with_website=10)
        report = compute_coverage_report(leads)
        assert report.total == 10
        assert report.phone_fill_rate == 1.0
        assert report.website_fill_rate == 1.0
        assert report.zero_web_presence == 0

    def test_none_filled(self):
        """0% fill rates."""
        leads = _make_leads(10, with_phone=0, with_website=0)
        report = compute_coverage_report(leads)
        assert report.phone_fill_rate == 0.0
        assert report.website_fill_rate == 0.0
        assert report.zero_web_presence == 10

    def test_partial_fill(self):
        """5 of 10 have phone, 2 of 10 have website."""
        leads = _make_leads(10, with_phone=5, with_website=2)
        report = compute_coverage_report(leads)
        assert report.phone_fill_rate == 0.5
        assert report.website_fill_rate == 0.2
        assert report.zero_web_presence == 8  # 10 - 2 with website

    def test_social_counts_as_web_presence(self):
        """Leads with social links but no website should NOT be counted as zero_web_presence."""
        leads = _make_leads(10, with_phone=0, with_website=0, with_social=3)
        report = compute_coverage_report(leads)
        assert report.zero_web_presence == 7  # 10 - 3 with social
        assert report.with_any_social == 3

    def test_empty_list(self):
        """Empty input should not crash."""
        report = compute_coverage_report([])
        assert report.total == 0
        assert report.phone_fill_rate == 0.0
        assert report.website_fill_rate == 0.0


class TestCoverageWarnings:
    """Verify WARNING fires below threshold and not above (Fix #4)."""

    def test_warning_fires_below_threshold(self, caplog):
        """Phone fill rate 4% (below 15%) -> WARNING logged."""
        leads = _make_leads(50, with_phone=2, with_website=2)
        with caplog.at_level(logging.WARNING):
            compute_coverage_report(leads, city="Karachi", category="dentist")
        assert any("LOW COVERAGE" in msg and "Phone" in msg for msg in caplog.messages)
        assert any("LOW COVERAGE" in msg and "Website" in msg for msg in caplog.messages)

    def test_no_warning_above_threshold(self, caplog):
        """Phone fill rate 50% (above 15%) -> no WARNING."""
        leads = _make_leads(10, with_phone=5, with_website=5)
        with caplog.at_level(logging.WARNING):
            compute_coverage_report(leads, city="London", category="restaurant")
        assert not any("LOW COVERAGE" in msg for msg in caplog.messages)

    def test_warning_at_exact_threshold(self, caplog):
        """At exactly 15% -> no warning (threshold is strictly less-than)."""
        # 15 of 100 = exactly 15%
        leads = _make_leads(100, with_phone=15, with_website=15)
        with caplog.at_level(logging.WARNING):
            compute_coverage_report(leads, city="Test", category="test")
        assert not any("LOW COVERAGE" in msg for msg in caplog.messages)


class TestBboxRetryWarning:
    """Verify bbox retry warning is logged when retries > 0 (Fix #3)."""

    def test_bbox_retry_warning(self, caplog):
        """bbox_retries=1 -> BBOX RETRY warning logged."""
        leads = _make_leads(5, with_phone=5, with_website=5)
        with caplog.at_level(logging.WARNING):
            report = compute_coverage_report(leads, city="Karachi", category="dentist", bbox_retries=1)
        assert report.bbox_retries == 1
        assert any("BBOX RETRY" in msg for msg in caplog.messages)

    def test_no_bbox_retry_warning(self, caplog):
        """bbox_retries=0 -> no BBOX RETRY warning."""
        leads = _make_leads(5, with_phone=5, with_website=5)
        with caplog.at_level(logging.WARNING):
            compute_coverage_report(leads, city="London", category="restaurant", bbox_retries=0)
        assert not any("BBOX RETRY" in msg for msg in caplog.messages)
