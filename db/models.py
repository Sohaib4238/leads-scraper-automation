"""
SQLAlchemy ORM models: Lead and ScrapeLog.
Compatible with both MySQL and SQLite.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all models."""
    pass


class Lead(Base):
    """A scraped business lead."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # -- Business info -----------------------------------------------------
    business_name = Column(String(500), nullable=True)
    category = Column(String(300), nullable=True)
    website = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(320), nullable=True)
    address = Column(String(1000), nullable=True)
    city = Column(String(200), nullable=True)
    country = Column(String(100), nullable=True)
    source_url = Column(String(2048), nullable=True)

    # -- Social links ------------------------------------------------------
    instagram = Column(String(500), nullable=True)
    facebook = Column(String(500), nullable=True)
    linkedin = Column(String(500), nullable=True)

    # -- Ratings -----------------------------------------------------------
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)

    # -- Pipeline status ---------------------------------------------------
    status = Column(String(20), nullable=False, default="new")
    score = Column(Integer, nullable=True)
    priority = Column(String(10), nullable=True)
    matched_services = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)

    # -- Technical & Performance Signals -----------------------------------
    response_time_ms = Column(Float, nullable=True)
    page_size_kb = Column(Float, nullable=True)

    # -- Contactability (v2) -----------------------------------------------
    contactable = Column(Boolean, nullable=False, default=False)

    # -- Discovery provenance (v2) -----------------------------------------
    discovery_sources = Column(JSON, nullable=True)

    # -- Timestamps --------------------------------------------------------
    created_at = Column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # -- Deduplication -----------------------------------------------------
    dedup_hash = Column(String(64), nullable=True, unique=True, index=True)

    # -- Indexes -----------------------------------------------------------
    __table_args__ = (
        Index("ix_leads_city", "city"),
        Index("ix_leads_status", "status"),
        Index("ix_leads_category", "category"),
        Index("ix_leads_phone", "phone"),
        Index("ix_leads_website", "website"),
        Index("ix_leads_contactable", "contactable"),
    )

    def __repr__(self) -> str:
        return (
            f"<Lead(id={self.id}, name={self.business_name!r}, "
            f"city={self.city!r}, contactable={self.contactable})>"
        )


class ScrapeLog(Base):
    """Audit log for each scrape batch run."""

    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(500), nullable=True)
    country = Column(String(100), nullable=True)
    city = Column(String(200), nullable=True)
    category = Column(String(300), nullable=True)
    requested_count = Column(Integer, nullable=True)

    # -- Source tracking (v2) ----------------------------------------------
    sources_used = Column(JSON, nullable=True)
    osm_count = Column(Integer, default=0)
    geoapify_count = Column(Integer, default=0)
    merged_count = Column(Integer, default=0)

    # -- Result counters ---------------------------------------------------
    found_count = Column(Integer, default=0)
    new_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)

    # -- Coverage stats (v2) -----------------------------------------------
    zero_web_presence_count = Column(Integer, default=0)
    phone_fill_rate = Column(Float, nullable=True)
    website_fill_rate = Column(Float, nullable=True)
    bbox_retries = Column(Integer, default=0)

    # -- Timestamps --------------------------------------------------------
    started_at = Column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScrapeLog(id={self.id}, query={self.query!r}, "
            f"new={self.new_count}, dupes={self.duplicate_count})>"
        )
