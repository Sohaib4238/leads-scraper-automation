"""
Batch Analyzer & Web Presence Enrichment Orchestrator for Phase 2 & 3.

Processes leads in configurable batch chunks (default batch_size=20),
crawls websites/social profiles, identifies technical & marketing defects,
captures performance metrics (response_time_ms, page_size_kb),
matches canonical services, calculates 0-100 scores, and commits each batch
to SQLite immediately to ensure fault tolerance.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import or_

from config.settings import setup_logging
from db.models import Lead
from db.session import init_db, get_session
from analyzer.crawler import LeadCrawler, CrawlResult
from matcher.service_matcher import ServiceMatcher
from scoring.lead_scorer import LeadScorer
from export.exporter import CITY_ALIASES, CATEGORY_SYNONYMS

logger = logging.getLogger(__name__)


@dataclass
class AnalyzeSummary:
    """Consolidated metrics from a batch analysis execution."""
    total_analyzed: int = 0
    failed_analyses: int = 0
    hot_count: int = 0
    warm_count: int = 0
    cold_count: int = 0
    actionable_count: int = 0
    needs_manual_lookup_count: int = 0
    flipped_to_contactable: int = 0
    service_breakdown: dict[str, int] = field(default_factory=dict)


def _get_city_filter_clauses(city: str):
    """Build SQLAlchemy OR filter clauses for city including multilingual aliases."""
    c_lower = city.strip().lower()
    variants = {city, c_lower}
    for _, aliases in CITY_ALIASES.items():
        if c_lower in aliases:
            variants.update(aliases)
    return or_(*[Lead.city.ilike(f"%{v}%") for v in variants])


def _get_category_filter_clauses(category: str):
    """Build SQLAlchemy OR filter clauses for category including synonyms."""
    cat_lower = category.strip().lower()
    variants = {category, cat_lower}
    for _, synonyms in CATEGORY_SYNONYMS.items():
        if cat_lower in synonyms:
            variants.update(synonyms)
    return or_(*[Lead.category.ilike(f"%{v}%") for v in variants])


def run_analyze_pipeline(
    limit: Optional[int] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    reanalyze_all: bool = False,
    batch_size: int = 20,
) -> AnalyzeSummary:
    """
    Run crawler, service matcher, and lead scoring on database leads in fault-tolerant batches.
    """
    setup_logging()
    init_db()

    summary = AnalyzeSummary()
    crawler = LeadCrawler()

    # Step 1: Collect lead IDs to process
    with get_session() as session:
        query = session.query(Lead.id)
        if not reanalyze_all:
            query = query.filter(Lead.status == "new")
        if city:
            query = query.filter(_get_city_filter_clauses(city))
        if category:
            query = query.filter(_get_category_filter_clauses(category))
        if limit:
            query = query.limit(limit)

        lead_ids = [r[0] for r in query.all()]

    total_leads = len(lead_ids)
    logger.info("Starting batch analysis for %d leads (batch_size=%d)", total_leads, batch_size)

    # Step 2: Process in incremental batches with immediate DB commits
    for i in range(0, total_leads, batch_size):
        batch_ids = lead_ids[i:i + batch_size]
        logger.info("Processing batch %d/%d (leads %d-%d of %d)", (i // batch_size) + 1, (total_leads + batch_size - 1) // batch_size, i + 1, min(i + batch_size, total_leads), total_leads)

        with get_session() as session:
            leads = session.query(Lead).filter(Lead.id.in_(batch_ids)).all()

            for lead in leads:
                try:
                    was_contactable = bool(lead.contactable)
                    crawl_result: Optional[CrawlResult] = None

                    # Target web presence to crawl
                    target_url = lead.website or lead.facebook or lead.instagram

                    if target_url:
                        try:
                            country_hint = lead.country or "US"
                            crawl_result = crawler.crawl_lead(target_url, country_code=country_hint)
                            
                            # Merge newly discovered contact details
                            if crawl_result.reachable:
                                if crawl_result.emails and not lead.email:
                                    lead.email = crawl_result.emails[0]
                                if crawl_result.phones and not lead.phone:
                                    lead.phone = crawl_result.phones[0]
                                if crawl_result.facebook and not lead.facebook:
                                    lead.facebook = crawl_result.facebook
                                if crawl_result.instagram and not lead.instagram:
                                    lead.instagram = crawl_result.instagram
                                if crawl_result.linkedin and not lead.linkedin:
                                    lead.linkedin = crawl_result.linkedin

                            # Store performance and technical signals
                            lead.response_time_ms = crawl_result.response_time_ms
                            lead.page_size_kb = crawl_result.page_size_kb

                        except Exception as crawl_exc:
                            logger.error("Crawl error on lead %d (%s): %s", lead.id, lead.business_name, crawl_exc)

                    # Update contactable flag (phone OR email available)
                    has_contact = bool((lead.phone and lead.phone.strip()) or (lead.email and lead.email.strip()))
                    lead.contactable = has_contact

                    if not was_contactable and lead.contactable:
                        summary.flipped_to_contactable += 1

                    # Match Canonical Services
                    matched_services, justification_tags = ServiceMatcher.match_services_with_reasons(lead, crawl_result)
                    lead.matched_services = json.dumps(matched_services)

                    # Score the lead
                    scored = LeadScorer.score_lead(lead, crawl_result, matched_services=matched_services, justification_tags=justification_tags)
                    lead.score = scored.score
                    lead.priority = scored.priority
                    lead.reason = scored.reason
                    lead.status = "analyzed"

                    # Track summary metrics
                    summary.total_analyzed += 1
                    if lead.priority == "HOT":
                        summary.hot_count += 1
                    elif lead.priority == "WARM":
                        summary.warm_count += 1
                    else:
                        summary.cold_count += 1

                    if lead.contactable:
                        summary.actionable_count += 1
                    else:
                        summary.needs_manual_lookup_count += 1

                    for srv in matched_services:
                        summary.service_breakdown[srv] = summary.service_breakdown.get(srv, 0) + 1

                except Exception as lead_exc:
                    summary.failed_analyses += 1
                    logger.error("Failed to analyze lead %d (%s): %s", lead.id, lead.business_name, lead_exc, exc_info=True)

            # Commit after each batch
            session.commit()
            logger.info("Committed batch of %d leads to database", len(leads))

    logger.info(
        "Analysis Complete: Total=%d, Failed=%d, HOT=%d, WARM=%d, COLD=%d, Actionable=%d, NeedsManual=%d, Flipped=%d",
        summary.total_analyzed, summary.failed_analyses, summary.hot_count, summary.warm_count, summary.cold_count,
        summary.actionable_count, summary.needs_manual_lookup_count, summary.flipped_to_contactable,
    )
    for srv, cnt in sorted(summary.service_breakdown.items(), key=lambda x: -x[1]):
        logger.info("  Service Breakdown: %-25s -> %d", srv, cnt)

    return summary
