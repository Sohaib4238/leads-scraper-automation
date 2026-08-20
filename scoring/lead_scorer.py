"""
Lead Scorer for Phase 2 & 3.

Scores business leads from 0 to 100 based on digital deficiency and technical signals.
Assigns priority tiers:
- HOT:  Score >= 60 (Major digital gaps, high sales opportunity)
- WARM: Score 30-59 (Moderate opportunities, partial web presence)
- COLD: Score < 30  (Well-optimized presence, low immediate agency need)

Generates a clear, human-readable reason string that directly incorporates
the exact matched canonical services and their justifications.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Union, Any

from config.settings import SCORING_WEIGHTS
from analyzer.crawler import CrawlResult
from matcher.service_matcher import ServiceMatcher, CANONICAL_SERVICES

logger = logging.getLogger(__name__)


@dataclass
class ScoredLead:
    """Scoring output containing score, priority, reason, and contact status."""
    score: int
    priority: str  # HOT, WARM, COLD
    reason: str
    contactable: bool
    lead_status: str  # actionable vs needs_manual_lookup


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


class LeadScorer:
    """Calculates lead opportunity scores and priority classifications."""

    @classmethod
    def score_lead(
        cls,
        lead_data: Any,
        crawl_result: Optional[CrawlResult] = None,
        matched_services: Optional[list[str]] = None,
        justification_tags: Optional[list[str]] = None,
    ) -> ScoredLead:
        """
        Compute opportunity score (0-100), priority tier, and synchronized explanation.
        """
        lead_dict = _to_dict(lead_data)
        score = 0
        score_breakdown: list[str] = []

        website = lead_dict.get("website")
        has_website = bool(website) and (not crawl_result or crawl_result.reachable)
        has_fb = bool(lead_dict.get("facebook") or (crawl_result and crawl_result.facebook))
        has_ig = bool(lead_dict.get("instagram") or (crawl_result and crawl_result.instagram))
        has_li = bool(lead_dict.get("linkedin") or (crawl_result and crawl_result.linkedin))
        social_count = sum([has_fb, has_ig, has_li])

        # 1. Website Presence (+30)
        if not has_website:
            score += SCORING_WEIGHTS.get("no_website", 30)
            score_breakdown.append("No active website (+30)")
        else:
            # 2. HTTPS (+10)
            if crawl_result and not crawl_result.is_https:
                score += SCORING_WEIGHTS.get("no_https", 10)
                score_breakdown.append("Website is not secured via HTTPS (+10)")

            # 3. SEO Gaps (+15)
            if crawl_result and crawl_result.seo_issues:
                score += SCORING_WEIGHTS.get("poor_seo", 15)
                issue_summary = ", ".join(crawl_result.seo_issues[:2])
                score_breakdown.append(f"SEO defects detected ({issue_summary}) (+15)")

            # 4. Mobile Viewport (+10)
            if crawl_result and not crawl_result.has_mobile_viewport:
                score += SCORING_WEIGHTS.get("no_mobile", 10)
                score_breakdown.append("Missing mobile viewport optimization (+10)")

        # 5. Social Media Presence (+10)
        if social_count == 0:
            score += SCORING_WEIGHTS.get("no_social", 10)
            score_breakdown.append("No active social media channels (+10)")

        # 6. Ratings (+15)
        rating = lead_dict.get("rating")
        if rating is not None and 0.0 < float(rating) < 4.0:
            score += SCORING_WEIGHTS.get("low_rating", 15)
            score_breakdown.append(f"Low public rating ({rating}/5.0) (+15)")

        # 7. Review Count (+10)
        review_count = lead_dict.get("review_count")
        if review_count is not None and 0 <= int(review_count) < 10:
            score += SCORING_WEIGHTS.get("few_reviews", 10)
            score_breakdown.append(f"Low review volume ({review_count} reviews) (+10)")

        # Cap score at 100
        score = min(score, 100)

        # Determine Priority Tier
        if score >= 60:
            priority = "HOT"
        elif score >= 30:
            priority = "WARM"
        else:
            priority = "COLD"

        # Determine Contactability
        has_phone = bool(lead_dict.get("phone") and str(lead_dict.get("phone")).strip())
        has_email = bool(lead_dict.get("email") and str(lead_dict.get("email")).strip())
        contactable = bool(lead_dict.get("contactable", False) or has_phone or has_email)
        lead_status = "actionable" if contactable else "needs_manual_lookup"

        # Match services and get synchronized justifications if not provided
        if matched_services is None or justification_tags is None:
            matched_services, justification_tags = ServiceMatcher.match_services_with_reasons(lead_dict, crawl_result)

        # Build fully synchronized, human-readable reason string
        reason_parts = [f"Priority {priority} (Score {score}/100)"]
        if score_breakdown:
            reason_parts.append("Signals: " + "; ".join(score_breakdown))
        if justification_tags:
            reason_parts.append("Recommended Services: " + "; ".join(justification_tags))
        elif matched_services:
            reason_parts.append("Recommended Services: " + ", ".join(matched_services))

        if contactable:
            contact_channel = "Direct Phone & Email" if (has_phone and has_email) else ("Direct Phone" if has_phone else "Direct Email")
            reason_parts.append(f"Actionable: {contact_channel} available for outreach.")
        else:
            reason_parts.append("Needs Manual Lookup: No direct phone or verified email found.")

        reason = " | ".join(reason_parts)

        return ScoredLead(
            score=score,
            priority=priority,
            reason=reason,
            contactable=contactable,
            lead_status=lead_status,
        )
