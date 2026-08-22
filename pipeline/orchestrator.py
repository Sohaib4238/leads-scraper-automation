"""
Pipeline orchestrator v2 -- multi-source discovery -> merge -> resolve -> store.

Error isolation: each provider runs in its own try/except. If Geoapify crashes,
OSM results are still saved. If OSM times out, Geoapify results are still saved.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config.settings import setup_logging, normalize_category
from db.session import get_session, init_db
from db.crud import create_lead, create_scrape_log, complete_scrape_log
from scraper.dedup import DeduplicationEngine
from scraper.osm_provider import OSMProvider
from scraper.geoapify_provider import GeoapifyProvider
from pipeline.discovery_merger import merge_discovery_results
from pipeline.coverage_reporter import compute_coverage_report, CoverageReport
from resolver.web_presence_resolver import resolve_web_presence

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary of a pipeline run."""
    query: str = ""
    total_found: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    osm_count: int = 0
    geoapify_count: int = 0
    merged_count: int = 0
    sources_used: list[str] = field(default_factory=list)
    coverage: CoverageReport = field(default_factory=CoverageReport)


def run_scrape_pipeline(
    country: str,
    city: str,
    category: str,
    count: int = 50,
    sources: list[str] | None = None,
) -> PipelineResult:
    """
    Full discovery pipeline:
    1. Init DB
    2. Create ScrapeLog
    3. Run selected providers (error-isolated)
    4. Merge results across providers
    5. Resolve web presence (social links + contactable flag)
    6. Dedup against existing DB leads
    7. Insert new leads (enforcing total unique count cap)
    8. Compute coverage report
    9. Finalize ScrapeLog
    """
    setup_logging()
    init_db()

    if sources is None:
        sources = ["osm", "geoapify"]

    canonical_category = normalize_category(category) or category
    query_str = f"{canonical_category} in {city}, {country}"
    result = PipelineResult(query=query_str, sources_used=sources)
    country_code = country.upper()

    with get_session() as session:
        log_entry = create_scrape_log(session, {
            "query": query_str,
            "country": country,
            "city": city,
            "category": canonical_category,
            "requested_count": count,
        })
        session.commit()

        try:
            # -- Step 1: Run discovery providers (error-isolated) ----------
            provider_results: dict[str, list[dict]] = {}
            bbox_retries = 0

            if "osm" in sources:
                try:
                    osm = OSMProvider()
                    osm_leads = osm.search(country, city, canonical_category, count)
                    provider_results["osm"] = osm_leads
                    result.osm_count = len(osm_leads)
                    bbox_retries = osm.bbox_retries
                    logger.info("OSM returned %d leads", len(osm_leads))
                except Exception as exc:
                    logger.error("OSM provider failed: %s", exc, exc_info=True)
                    result.error_count += 1

            if "geoapify" in sources:
                try:
                    geo = GeoapifyProvider()
                    geo_leads = geo.search(country, city, canonical_category, count)
                    provider_results["geoapify"] = geo_leads
                    result.geoapify_count = len(geo_leads)
                    logger.info("Geoapify returned %d leads", len(geo_leads))
                except Exception as exc:
                    logger.error("Geoapify provider failed: %s", exc, exc_info=True)
                    result.error_count += 1

            result.total_found = sum(len(v) for v in provider_results.values())

            # -- Step 2: Merge across providers ----------------------------
            merged_leads = merge_discovery_results(provider_results, country_code=country_code)
            result.merged_count = len(merged_leads)

            # -- Step 3: Resolve web presence ------------------------------
            resolved_leads = resolve_web_presence(merged_leads)

            # -- Step 4: Dedup against DB + insert with true total cap -----
            dedup = DeduplicationEngine()

            for lead_data in resolved_leads:
                # Enforce total unique lead count cap
                if count > 0 and result.new_count >= count:
                    logger.info(
                        "Reached requested total cap of %d new unique leads. Halting ingestion.", count
                    )
                    break

                try:
                    # Fill in city/country if not set by provider
                    if not lead_data.get("city"):
                        lead_data["city"] = city
                    if not lead_data.get("country"):
                        lead_data["country"] = country

                    # Normalize category to canonical name
                    raw_lead_cat = lead_data.get("category")
                    lead_data["category"] = normalize_category(raw_lead_cat) or canonical_category

                    if dedup.is_duplicate(session, lead_data, country_code):
                        result.duplicate_count += 1
                        continue

                    # Normalize and insert using create_lead
                    normalized = dedup.normalize_lead_for_storage(lead_data, country_code)
                    create_lead(session, normalized)
                    result.new_count += 1

                except Exception as exc:
                    logger.error(
                        "Error processing lead %r: %s",
                        lead_data.get("business_name"), exc,
                    )
                    result.error_count += 1

            session.commit()

            # -- Step 5: Coverage report -----------------------------------
            result.coverage = compute_coverage_report(
                resolved_leads[:result.new_count if result.new_count > 0 else len(resolved_leads)],
                city=city,
                category=canonical_category,
                bbox_retries=bbox_retries,
            )

            # -- Step 6: Finalize scrape log -------------------------------
            log_entry.sources_used = sources
            log_entry.osm_count = result.osm_count
            log_entry.geoapify_count = result.geoapify_count
            log_entry.merged_count = result.merged_count
            log_entry.zero_web_presence_count = result.coverage.zero_web_presence
            log_entry.phone_fill_rate = result.coverage.phone_fill_rate
            log_entry.website_fill_rate = result.coverage.website_fill_rate
            log_entry.bbox_retries = bbox_retries

            complete_scrape_log(
                session,
                log_id=log_entry.id,
                found=result.total_found,
                new=result.new_count,
                duplicates=result.duplicate_count,
                errors=result.error_count,
            )
            session.commit()

        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            session.rollback()

    return result
