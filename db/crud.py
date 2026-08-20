"""
CRUD helpers for Lead and ScrapeLog models.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import Lead, ScrapeLog


# ── Lead CRUD ──────────────────────────────────────────────────────────


def create_lead(session: Session, lead_data: dict) -> Lead:
    """Insert a new Lead row and flush (but don't commit — caller controls tx)."""
    lead = Lead(**lead_data)
    session.add(lead)
    session.flush()
    return lead


def get_lead_by_dedup_hash(session: Session, dedup_hash: str) -> Optional[Lead]:
    """Fast lookup by unique dedup_hash index."""
    return session.query(Lead).filter(Lead.dedup_hash == dedup_hash).first()


def get_lead_by_phone(session: Session, normalized_phone: str) -> Optional[Lead]:
    """Lookup by normalized phone number."""
    if not normalized_phone:
        return None
    return session.query(Lead).filter(Lead.phone == normalized_phone).first()


def get_lead_by_website_domain(session: Session, domain: str) -> Optional[Lead]:
    """Lookup by domain substring in the website field."""
    if not domain:
        return None
    return (
        session.query(Lead)
        .filter(Lead.website.isnot(None))
        .filter(Lead.website.contains(domain))
        .first()
    )


def get_lead_by_email(session: Session, email: str) -> Optional[Lead]:
    """Lookup by email (case-insensitive via lowercase storage)."""
    if not email:
        return None
    return session.query(Lead).filter(Lead.email == email.lower()).first()


def get_leads_by_city(session: Session, city: str) -> list[Lead]:
    """Return all leads in a given city (for fuzzy name+address matching)."""
    if not city:
        return []
    return session.query(Lead).filter(Lead.city == city).all()


def list_leads(
    session: Session,
    status: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 500,
) -> list[Lead]:
    """List leads with optional filters."""
    query = session.query(Lead)
    if status:
        query = query.filter(Lead.status == status)
    if city:
        query = query.filter(Lead.city == city)
    if category:
        query = query.filter(Lead.category == category)
    if priority:
        query = query.filter(Lead.priority == priority)
    return query.order_by(Lead.created_at.desc()).limit(limit).all()


def update_lead(session: Session, lead_id: int, updates: dict) -> Optional[Lead]:
    """Update specific fields on a Lead. Returns the updated lead or None."""
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if lead is None:
        return None
    for key, value in updates.items():
        if hasattr(lead, key):
            setattr(lead, key, value)
    lead.updated_at = datetime.now(timezone.utc)
    session.flush()
    return lead


# ── ScrapeLog CRUD ─────────────────────────────────────────────────────


def create_scrape_log(session: Session, log_data: dict) -> ScrapeLog:
    """Create a new ScrapeLog entry for a batch run."""
    log = ScrapeLog(**log_data)
    session.add(log)
    session.flush()
    return log


def complete_scrape_log(
    session: Session,
    log_id: int,
    found: int,
    new: int,
    duplicates: int,
    errors: int,
) -> Optional[ScrapeLog]:
    """Finalize a ScrapeLog entry with result counts."""
    log = session.query(ScrapeLog).filter(ScrapeLog.id == log_id).first()
    if log is None:
        return None
    log.found_count = found
    log.new_count = new
    log.duplicate_count = duplicates
    log.error_count = errors
    log.completed_at = datetime.now(timezone.utc)
    session.flush()
    return log
