"""
Unit tests for matcher/service_matcher.py

Verifies:
- Canonical 9 agency service names are strictly used
- No non-spec service names are returned
- Service matching rules trigger correctly without over-triggering
- Synchronized justifications are returned
"""

import pytest
from matcher.service_matcher import ServiceMatcher, CANONICAL_SERVICES, VALID_SERVICES
from analyzer.crawler import CrawlResult


class TestServiceMatcher:
    """Test suite for ServiceMatcher rules."""

    def test_canonical_service_names_only(self):
        """Ensure only the 9 canonical services are ever returned."""
        lead_data = {
            "business_name": "Test Clinic",
            "category": "dentist",
            "website": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "rating": 2.5,
            "review_count": 2,
        }
        services = ServiceMatcher.match_services(lead_data, crawl_result=None)
        for s in services:
            assert s in CANONICAL_SERVICES
            assert s in VALID_SERVICES

    def test_no_website_rule(self):
        """Missing website should trigger Web Development, SEO, and Google Ads for high-intent business."""
        lead_data = {
            "business_name": "Karachi Dentists",
            "category": "dentist",
            "website": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
        }
        services, reasons = ServiceMatcher.match_services_with_reasons(lead_data, crawl_result=None)
        assert "Web Development" in services
        assert "SEO" in services
        assert any("no active website found" in r for r in reasons)

    def test_weak_seo_rule(self):
        """Technical SEO issues should trigger SEO service."""
        lead_data = {
            "business_name": "Berlin Smiles",
            "category": "dentist",
            "website": "https://berlinsmiles.de",
            "facebook": "https://facebook.com/berlinsmiles",
            "instagram": "https://instagram.com/berlinsmiles",
            "linkedin": "https://linkedin.com/company/berlinsmiles",
            "rating": 4.8,
            "review_count": 50,
        }
        crawl = CrawlResult(
            url="https://berlinsmiles.de",
            reachable=True,
            seo_issues=["missing_title", "no_mobile_viewport"],
        )
        services = ServiceMatcher.match_services(lead_data, crawl_result=crawl)
        assert "SEO" in services

    def test_ecommerce_rule(self):
        """E-commerce detection on retail clothing store should trigger Google Shopping and Web App Development."""
        lead_data = {
            "business_name": "Berlin Boutique",
            "category": "clothing store",
            "website": "https://berlinboutique.de",
            "facebook": "https://facebook.com/berlinboutique",
            "instagram": "https://instagram.com/berlinboutique",
            "linkedin": None,
            "rating": 4.5,
            "review_count": 25,
        }
        crawl = CrawlResult(
            url="https://berlinboutique.de",
            reachable=True,
            has_ecommerce=True,
        )
        services = ServiceMatcher.match_services(lead_data, crawl_result=crawl)
        assert "Google Shopping" in services
        assert "Web App Development" in services

    def test_missing_booking_form_rule(self):
        """High-intent clinic lacking booking system should trigger AI Automation."""
        lead_data = {
            "business_name": "Dental Surgery",
            "category": "dentist",
            "website": "https://dentalsurgery.pk",
            "facebook": "https://facebook.com/dentalsurgery",
            "instagram": None,
            "linkedin": None,
        }
        crawl = CrawlResult(
            url="https://dentalsurgery.pk",
            reachable=True,
            has_booking_form=False,
        )
        services = ServiceMatcher.match_services(lead_data, crawl_result=crawl)
        assert "AI Automation" in services

    def test_well_optimized_cold_lead_minimal_services(self):
        """A well-optimized clinic with booking system and complete social presence should have minimal service needs."""
        lead_data = {
            "business_name": "Elite Dental Spa",
            "category": "dentist",
            "website": "https://elitedental.com",
            "facebook": "https://facebook.com/elite",
            "instagram": "https://instagram.com/elite",
            "linkedin": "https://linkedin.com/company/elite",
            "rating": 4.9,
            "review_count": 250,
        }
        crawl = CrawlResult(
            url="https://elitedental.com",
            reachable=True,
            is_https=True,
            has_booking_form=True,
            has_ecommerce=False,
            seo_issues=[],
        )
        services = ServiceMatcher.match_services(lead_data, crawl_result=crawl)
        # Should not trigger Google Shopping, Web Development, or Web App Development
        assert "Google Shopping" not in services
        assert "Web Development" not in services
        assert "Web App Development" not in services
