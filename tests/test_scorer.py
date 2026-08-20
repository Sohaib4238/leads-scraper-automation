"""
Unit tests for scoring/lead_scorer.py

Verifies:
- Opportunity score computation matching weights
- Priority levels: HOT (>=60), WARM (30-59), COLD (<30)
- Actionable vs Needs Manual Lookup split based on contactable flag
- Informative reason text generation citing specific signals
"""

import pytest
from scoring.lead_scorer import LeadScorer
from analyzer.crawler import CrawlResult


class TestLeadScorer:
    """Verify lead scoring, priority mapping, and actionability classification."""

    def test_hot_priority_no_website_no_social(self):
        """No website (+30) + No social (+10) + Low reviews (+10) = 50 -> WARM; with no rating/review adjust."""
        lead_data = {
            "business_name": "Local Store",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "rating": 3.2,       # +15
            "review_count": 4,   # +10
            "contactable": False,
        }
        # 30 (no web) + 10 (no social) + 15 (low rating) + 10 (few reviews) = 65 -> HOT
        scored = LeadScorer.score_lead(lead_data, crawl_result=None)
        assert scored.score == 65
        assert scored.priority == "HOT"
        assert scored.lead_status == "needs_manual_lookup"
        assert scored.contactable is False
        assert "Needs Manual Lookup" in scored.reason

    def test_actionable_lead_with_phone(self):
        """Lead with phone should be marked actionable even if high score."""
        lead_data = {
            "business_name": "Dentist with Phone",
            "website": None,
            "phone": "+923001234567",
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "rating": 3.5,       # +15
            "review_count": 2,   # +10
            "contactable": True,
        }
        # 30 + 10 + 15 + 10 = 65 -> HOT
        scored = LeadScorer.score_lead(lead_data, crawl_result=None)
        assert scored.score == 65
        assert scored.priority == "HOT"
        assert scored.lead_status == "actionable"
        assert scored.contactable is True
        assert "Actionable" in scored.reason

    def test_cold_priority_well_optimized_site(self):
        """Secure HTTPS site with good SEO, active social, good reviews -> COLD priority."""
        lead_data = {
            "business_name": "Elite Dental Hospital",
            "website": "https://elitedental.com",
            "phone": "+922135821955",
            "email": "contact@elitedental.com",
            "facebook": "https://facebook.com/elitedental",
            "instagram": "https://instagram.com/elitedental",
            "linkedin": "https://linkedin.com/company/elitedental",
            "rating": 4.8,
            "review_count": 150,
            "contactable": True,
        }
        crawl = CrawlResult(
            url="https://elitedental.com",
            reachable=True,
            is_https=True,
            has_mobile_viewport=True,
            seo_issues=[],
            has_booking_form=True,
        )
        scored = LeadScorer.score_lead(lead_data, crawl_result=crawl)
        assert scored.score == 0
        assert scored.priority == "COLD"
        assert scored.lead_status == "actionable"
        assert scored.contactable is True

    def test_website_technical_issues_weight(self):
        """Non-HTTPS (+10), SEO issues (+15), No mobile viewport (+10), No social (+10) -> 45 -> WARM."""
        lead_data = {
            "business_name": "Outdated Site Clinic",
            "website": "http://outdatedclinic.com",
            "phone": "+923001112233",
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "rating": 4.5,
            "review_count": 25,
            "contactable": True,
        }
        crawl = CrawlResult(
            url="http://outdatedclinic.com",
            reachable=True,
            is_https=False,
            has_mobile_viewport=False,
            seo_issues=["missing_meta_description"],
            has_booking_form=False,
        )
        scored = LeadScorer.score_lead(lead_data, crawl_result=crawl)
        # 10 (no https) + 15 (seo) + 10 (no mobile) + 10 (no social) = 45 -> WARM
        assert scored.score == 45
        assert scored.priority == "WARM"
        assert scored.lead_status == "actionable"
