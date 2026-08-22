"""
One-time database migration script: SQLite (data/leads.db) -> MySQL.

Reads all historical business leads and scrape audit logs from SQLite
and transfers them into the target MySQL database, preserving all
columns, JSON arrays/objects, technical signals, and timestamps.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from config.settings import DATA_DIR, DATABASE_URL
from db.models import Base, Lead, ScrapeLog

console = Console(legacy_windows=False)
logger = logging.getLogger(__name__)


def mask_url_password(url: str) -> str:
    """Mask password in connection string for clean terminal display."""
    if "@" in url:
        try:
            proto_auth, host_db = url.split("@", 1)
            proto, auth = proto_auth.split("://", 1)
            if ":" in auth:
                user, _ = auth.split(":", 1)
                return f"{proto}://{user}:****@{host_db}"
        except Exception:
            pass
    return url


def migrate_sqlite_to_mysql(sqlite_path: Path = None, mysql_url: str = None) -> bool:
    """
    Migrate all leads and scrape logs from SQLite to MySQL.
    """
    if sqlite_path is None:
        sqlite_path = DATA_DIR / "leads.db"

    if mysql_url is None:
        mysql_url = DATABASE_URL

    if not sqlite_path.exists():
        console.print(f"[bold red]Error:[/bold red] SQLite database file not found at {sqlite_path}")
        return False

    console.print(f"\n[bold blue]Starting SQLite -> Database Migration[/bold blue]")
    console.print(f"Source SQLite: [cyan]{sqlite_path}[/cyan]")
    console.print(f"Target DB:     [cyan]{mask_url_password(mysql_url)}[/cyan]\n")

    # Connect to SQLite
    sqlite_engine = create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
    )
    SqliteSession = sessionmaker(bind=sqlite_engine)

    # Connect to Target DB (MySQL)
    try:
        mysql_engine = create_engine(
            mysql_url,
            pool_pre_ping=True,
            pool_recycle=3600 if "mysql" in mysql_url.lower() else -1,
        )
        # Verify connection
        with mysql_engine.connect() as conn:
            conn.execute(select(1))
    except Exception as exc:
        console.print(f"[bold red]Connection to target database failed:[/bold red] {exc}")
        console.print("[dim]Check that your MySQL server is running and credentials in .env are correct.[/dim]\n")
        return False

    # Create target tables
    console.print("-> Initializing schema and indexes...")
    Base.metadata.create_all(bind=mysql_engine)
    MysqlSession = sessionmaker(bind=mysql_engine)

    with SqliteSession() as src_session, MysqlSession() as dst_session:
        # 1. Migrate Leads
        sqlite_leads = src_session.query(Lead).order_by(Lead.id.asc()).all()
        console.print(f"-> Reading {len(sqlite_leads)} leads from SQLite...")

        migrated_leads = 0
        skipped_leads = 0

        for lead in sqlite_leads:
            # Check if lead dedup_hash exists in MySQL
            existing = None
            if lead.dedup_hash:
                existing = dst_session.query(Lead).filter(Lead.dedup_hash == lead.dedup_hash).first()

            if existing:
                skipped_leads += 1
                continue

            # Parse JSON fields if stored as raw strings in SQLite
            matched_svcs = lead.matched_services
            if isinstance(matched_svcs, str):
                try:
                    matched_svcs = json.loads(matched_svcs)
                except Exception:
                    pass

            disc_sources = lead.discovery_sources
            if isinstance(disc_sources, str):
                try:
                    disc_sources = json.loads(disc_sources)
                except Exception:
                    pass

            new_lead = Lead(
                business_name=lead.business_name,
                category=lead.category,
                website=lead.website,
                phone=lead.phone,
                email=lead.email,
                address=lead.address,
                city=lead.city,
                country=lead.country,
                source_url=lead.source_url,
                instagram=lead.instagram,
                facebook=lead.facebook,
                linkedin=lead.linkedin,
                rating=lead.rating,
                review_count=lead.review_count,
                status=lead.status,
                score=lead.score,
                priority=lead.priority,
                matched_services=matched_svcs,
                reason=lead.reason,
                response_time_ms=lead.response_time_ms,
                page_size_kb=lead.page_size_kb,
                contactable=lead.contactable,
                discovery_sources=disc_sources,
                created_at=lead.created_at,
                updated_at=lead.updated_at,
                dedup_hash=lead.dedup_hash,
            )
            dst_session.add(new_lead)
            migrated_leads += 1

        # 2. Migrate ScrapeLogs
        sqlite_logs = src_session.query(ScrapeLog).order_by(ScrapeLog.id.asc()).all()
        console.print(f"-> Reading {len(sqlite_logs)} scrape audit logs from SQLite...")

        migrated_logs = 0
        for log in sqlite_logs:
            sources_used = log.sources_used
            if isinstance(sources_used, str):
                try:
                    sources_used = json.loads(sources_used)
                except Exception:
                    pass

            new_log = ScrapeLog(
                query=log.query,
                country=log.country,
                city=log.city,
                category=log.category,
                requested_count=log.requested_count,
                sources_used=sources_used,
                osm_count=log.osm_count,
                geoapify_count=log.geoapify_count,
                merged_count=log.merged_count,
                found_count=log.found_count,
                new_count=log.new_count,
                duplicate_count=log.duplicate_count,
                error_count=log.error_count,
                zero_web_presence_count=log.zero_web_presence_count,
                phone_fill_rate=log.phone_fill_rate,
                website_fill_rate=log.website_fill_rate,
                bbox_retries=log.bbox_retries,
                started_at=log.started_at,
                completed_at=log.completed_at,
            )
            dst_session.add(new_log)
            migrated_logs += 1

        # Commit all target database inserts
        dst_session.commit()

        # Query final count for verification
        final_leads_count = dst_session.query(func.count(Lead.id)).scalar()
        final_logs_count = dst_session.query(func.count(ScrapeLog.id)).scalar()

    # Display Results Summary Table
    table = Table(title="Database Migration Summary", show_header=True, header_style="bold cyan")
    table.add_column("Entity / Table", style="bold")
    table.add_column("SQLite (Source)", justify="right")
    table.add_column("Migrated (New)", justify="right", style="green")
    table.add_column("Target DB (Total)", justify="right", style="bold green")

    table.add_row("Leads", str(len(sqlite_leads)), str(migrated_leads), str(final_leads_count))
    table.add_row("Scrape Logs", str(len(sqlite_logs)), str(migrated_logs), str(final_logs_count))

    console.print()
    console.print(table)
    console.print("\n[bold green]Migration completed successfully![/bold green]\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite leads.db to MySQL")
    parser.add_argument("--sqlite-path", type=str, default=None, help="Path to source SQLite .db file")
    parser.add_argument("--mysql-url", type=str, default=None, help="Target MySQL connection URL")
    args = parser.parse_args()

    src = Path(args.sqlite_path) if args.sqlite_path else None
    success = migrate_sqlite_to_mysql(sqlite_path=src, mysql_url=args.mysql_url)
    sys.exit(0 if success else 1)
