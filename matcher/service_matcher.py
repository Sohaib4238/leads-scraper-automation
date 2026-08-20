"""
Service Matcher for Phase 2 & 3.

Strictly matches leads against the 9 canonical agency services:
1. Web Development
2. Web App Development
3. Mobile App Development
4. SEO
5. Social Media Marketing
6. Social Media Management
7. Google Ads
8. Google Shopping
9. AI Automation

Synchronized with LeadScorer to provide explicit justification tags.
Eliminates over-triggering with strict intent and category guards.
"""

import logging
from typing import Optional, Union, Any

from analyzer.crawler import CrawlResult

logger = logging.getLogger(__name__)

# Strict canonical 9 agency services
CANONICAL_SERVICES = [
    "Web Development",
    "Web App Development",
    "Mobile App Development",
    "SEO",
    "Social Media Marketing",
    "Social Media Management",
    "Google Ads",
    "Google Shopping",
    "AI Automation",
]
VALID_SERVICES = CANONICAL_SERVICES  # Backwards compatibility alias

# High-intent commercial categories where paid advertising is competitive
HIGH_COMMERCIAL_INTENT_CATEGORIES = {
    "dentist", "dental", "dental clinic", "orthodontist",
    "doctor", "clinic", "hospital", "medical clinic",
    "lawyer", "attorney", "law firm", "legal",
    "accountant", "accounting", "tax", "cpa",
    "real estate", "estate agent", "realtor", "property",
    "car repair", "auto repair", "mechanic", "hvac", "plumber", "electrician",
    "plastic surgery", "dermatologist", "cosmetic clinic",
}

# Categories that naturally require appointments or lead capture automation
AUTOMATION_INTENT_CATEGORIES = {
    "dentist", "dental", "dental clinic", "orthodontist",
    "doctor", "clinic", "hospital", "medical clinic",
    "lawyer", "attorney", "law firm", "legal",
    "accountant", "accounting",
    "real estate", "estate agent", "realtor", "property",
    "salon", "hairdresser", "spa", "beauty", "massage",
    "gym", "fitness", "yoga", "crossfit",
    "hotel", "car repair", "auto repair",
}

# Strictly physical / clinical categories where Google Shopping is irrelevant
NON_ECOMMERCE_CATEGORIES = {
    "dentist", "dental", "dental clinic", "orthodontist",
    "doctor", "clinic", "hospital", "medical clinic",
    "lawyer", "attorney", "law firm", "legal",
    "accountant", "accounting",
    "barber", "hairdresser", "salon",
    "car repair", "auto repair", "mechanic",
    "school", "university",
}


def _to_dict(lead_data: Any) -> dict:
    """Normalize SQLAlchemy Lead model or dictionary to dict."""
    if isinstance(lead_data, dict):
        return lead_data
    return {
        "business_name": getattr(lead_data, "business_name", None),
        "website": getattr(lead_data, "website", None),
        "phone": getattr(lead_data, "phone", None),
        "email": getattr(lead_data, "email", None),
        "category": getattr(lead_data, "category", None),
        "city": getattr(lead_data, "city", None),
        "country": getattr(lead_data, "country", None),
        "facebook": getattr(lead_data, "facebook", None),
        "instagram": getattr(lead_data, "instagram", None),
        "linkedin": getattr(lead_data, "linkedin", None),
        "rating": getattr(lead_data, "rating", None),
        "review_count": getattr(lead_data, "review_count", None),
        "contactable": getattr(lead_data, "contactable", False),
    }


class ServiceMatcher:
    """Evaluates website and discovery signals to recommend canonical services."""

    @classmethod
    def match_services_with_reasons(
        cls, lead_data: Any, crawl_result: Optional[CrawlResult] = None
    ) -> tuple[list[str], list[str]]:
        """
        Identify service recommendations and their specific justifications.
        Returns:
            (matched_services, justification_strings)
        """
        lead_dict = _to_dict(lead_data)
        services: set[str] = set()
        justifications: list[str] = []

        website = lead_dict.get("website")
        category = (lead_dict.get("category") or "").lower().strip()

        has_website = bool(website) and (not crawl_result or crawl_result.reachable)
        has_fb = bool(lead_dict.get("facebook") or (crawl_result and crawl_result.facebook))
        has_ig = bool(lead_dict.get("instagram") or (crawl_result and crawl_result.instagram))
        has_li = bool(lead_dict.get("linkedin") or (crawl_result and crawl_result.linkedin))
        social_count = sum([has_fb, has_ig, has_li])

        rating = lead_dict.get("rating")
        review_count = lead_dict.get("review_count")
        has_low_reviews = review_count is not None and int(review_count) < 10
        has_low_rating = rating is not None and float(rating) < 4.0

        # ------------------------------------------------------------------
        # 1. "Web Development"
        # ------------------------------------------------------------------
        if not has_website:
            services.add("Web Development")
            justifications.append("Web Development (no active website found)")

        # ------------------------------------------------------------------
        # 2. "SEO"
        # ------------------------------------------------------------------
        if crawl_result and crawl_result.seo_issues:
            issues_str = ", ".join(crawl_result.seo_issues[:2])
            services.add("SEO")
            justifications.append(f"SEO (technical defects: {issues_str})")
        elif not has_website:
            services.add("SEO")
            justifications.append("SEO (needs initial search visibility & indexing)")

        # ------------------------------------------------------------------
        # 3. "Social Media Marketing"
        # ------------------------------------------------------------------
        if social_count == 0:
            services.add("Social Media Marketing")
            justifications.append("Social Media Marketing (no active social channels detected)")
        elif has_low_reviews or has_low_rating:
            services.add("Social Media Marketing")
            justifications.append("Social Media Marketing (brand awareness & reputation boost)")

        # ------------------------------------------------------------------
        # 4. "Social Media Management"
        # ------------------------------------------------------------------
        if 0 < social_count < 2:
            services.add("Social Media Management")
            justifications.append("Social Media Management (multi-channel expansion)")

        # ------------------------------------------------------------------
        # 5. "Google Ads"
        # ------------------------------------------------------------------
        is_high_intent = any(c in category for c in HIGH_COMMERCIAL_INTENT_CATEGORIES)
        if is_high_intent and (has_low_reviews or not has_website or (crawl_result and crawl_result.seo_issues)):
            services.add("Google Ads")
            justifications.append("Google Ads (high commercial search demand & acquisition intent)")

        # ------------------------------------------------------------------
        # 6. "Google Shopping"
        # ------------------------------------------------------------------
        is_non_ecomm = any(c in category for c in NON_ECOMMERCE_CATEGORIES)
        if not is_non_ecomm and crawl_result and crawl_result.has_ecommerce:
            services.add("Google Shopping")
            justifications.append("Google Shopping (e-commerce catalog detected)")

        # ------------------------------------------------------------------
        # 7. "AI Automation"
        # ------------------------------------------------------------------
        is_auto_category = any(c in category for c in AUTOMATION_INTENT_CATEGORIES)
        if is_auto_category and crawl_result and not crawl_result.has_booking_form:
            services.add("AI Automation")
            justifications.append("AI Automation (missing automated booking / lead capture)")

        # ------------------------------------------------------------------
        # 8. "Web App Development"
        # ------------------------------------------------------------------
        if crawl_result and crawl_result.has_ecommerce:
            services.add("Web App Development")
            justifications.append("Web App Development (custom checkout / portal workflows)")

        # ------------------------------------------------------------------
        # 9. "Mobile App Development"
        # ------------------------------------------------------------------
        is_app_candidate = (
            (crawl_result and crawl_result.has_ecommerce) or
            ("gym" in category or "fitness" in category or "hotel" in category or "cafe" in category or "restaurant" in category)
        )
        if is_app_candidate and not is_non_ecomm:
            services.add("Mobile App Development")
            justifications.append("Mobile App Development (customer loyalty & recurring ordering)")

        # Filter strictly to canonical list
        canonical_matches = [s for s in CANONICAL_SERVICES if s in services]
        return sorted(canonical_matches), justifications

    @classmethod
    def match_services(
        cls, lead_data: Any, crawl_result: Optional[CrawlResult] = None
    ) -> list[str]:
        """Convenience method returning matched service names only."""
        services, _ = cls.match_services_with_reasons(lead_data, crawl_result)
        return services
