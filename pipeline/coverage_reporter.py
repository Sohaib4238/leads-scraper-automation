"""
Coverage & Data Quality Reporter for Phase 1 v2.

Computes fill rates (phone, website, email, social) for discovered leads,
detects zero-web-presence leads, and logs warnings when fill rates fall
below the configured threshold (COVERAGE_WARNING_THRESHOLD = 0.15).

Also tracks bbox retry events (Fix #3) to confirm the dynamic bounding-box
shrinking mechanism is firing when Overpass times out.
"""

import logging
from dataclasses import dataclass

from config.settings import COVERAGE_WARNING_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class CoverageReport:
    """Coverage statistics for a single search run."""
    total: int = 0
    with_phone: int = 0
    with_website: int = 0
    with_email: int = 0
    with_any_social: int = 0
    zero_web_presence: int = 0  # no website AND no social
    bbox_retries: int = 0       # Fix #3: bbox shrinks that occurred

    @property
    def phone_fill_rate(self) -> float:
        return self.with_phone / self.total if self.total else 0.0

    @property
    def website_fill_rate(self) -> float:
        return self.with_website / self.total if self.total else 0.0

    @property
    def email_fill_rate(self) -> float:
        return self.with_email / self.total if self.total else 0.0

    @property
    def social_fill_rate(self) -> float:
        return self.with_any_social / self.total if self.total else 0.0

    @property
    def zero_web_presence_count(self) -> int:
        return self.zero_web_presence

    @property
    def contactable_count(self) -> int:
        return self.with_phone + self.with_email

    @property
    def needs_manual_lookup_count(self) -> int:
        return max(0, self.total - self.contactable_count)


class CoverageReporter:
    """Computes coverage stats and issues warnings on low-quality discovery batches."""

    @staticmethod
    def compute_coverage(leads: list[dict], bbox_retries: int = 0) -> CoverageReport:
        """
        Analyze a list of resolved lead dicts and return coverage statistics.
        """
        report = CoverageReport(total=len(leads), bbox_retries=bbox_retries)

        if not leads:
            return report

        for lead in leads:
            has_phone = bool(lead.get("phone"))
            has_website = bool(lead.get("website"))
            has_email = bool(lead.get("email"))
            has_social = bool(
                lead.get("facebook")
                or lead.get("instagram")
                or lead.get("linkedin")
            )

            if has_phone:
                report.with_phone += 1
            if has_website:
                report.with_website += 1
            if has_email:
                report.with_email += 1
            if has_social:
                report.with_any_social += 1
            if not has_website and not has_social:
                report.zero_web_presence += 1

        return report

    @staticmethod
    def log_warnings(report: CoverageReport, category: str, city: str) -> None:
        """
        Emit WARNING logs if fill rates are below threshold.
        """
        if report.total == 0:
            return

        if report.phone_fill_rate < COVERAGE_WARNING_THRESHOLD:
            logger.warning(
                "LOW COVERAGE: Phone fill rate for %s in %s is only %.0f%% "
                "(threshold: %.0f%%). Leads in this batch have limited direct contact info.",
                category, city,
                report.phone_fill_rate * 100,
                COVERAGE_WARNING_THRESHOLD * 100,
            )

        if report.website_fill_rate < COVERAGE_WARNING_THRESHOLD:
            logger.warning(
                "LOW COVERAGE: Website fill rate for %s in %s is only %.0f%% "
                "(threshold: %.0f%%). The crawler (Phase 2) will have limited targets for website analysis.",
                category, city,
                report.website_fill_rate * 100,
                COVERAGE_WARNING_THRESHOLD * 100,
            )

        if report.bbox_retries > 0:
            logger.warning(
                "BBOX RETRY: Overpass query required %d bounding-box shrinks to complete.",
                report.bbox_retries,
            )


def compute_coverage_report(
    leads: list[dict],
    city: str = "",
    category: str = "",
    bbox_retries: int = 0,
) -> CoverageReport:
    """Compute fill rates and log warnings if below threshold."""
    report = CoverageReporter.compute_coverage(leads, bbox_retries=bbox_retries)
    CoverageReporter.log_warnings(report, category=category, city=city)
    return report
