"""
Lead Scraper Automation CLI.

Commands:
- `scrape`: Discover leads via multi-source search (OSM + Geoapify) and merge with dedup.
- `analyze`: Crawl websites, extract contacts, performance signals, match canonical services, and score leads.
- `export`: Export filtered leads to CSV or XLSX with multi-criteria AND logic.
- `run`: Chain full pipeline (Discovery -> Analyze & Enrich -> Multi-Filter Export).
- `info`: Display database health, fill rates, and service breakdown metrics.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from config.settings import setup_logging
from db.session import init_db, get_session
from db.models import Lead
from pipeline.orchestrator import run_scrape_pipeline
from pipeline.analyzer_orchestrator import run_analyze_pipeline
from export.exporter import LeadExporter

app = typer.Typer(
    name="lead-scraper",
    help="Professional Lead Scraper & Automation CLI",
    add_completion=False,
)
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def scrape(
    country: str = typer.Option(..., "--country", "-C", help="2-letter ISO country code (e.g. PK, DE, GB, US, AE)"),
    city: str = typer.Option(..., "--city", "-c", help="City name to search (e.g. Karachi, Berlin, London, Dubai)"),
    category: str = typer.Option(..., "--category", "-k", help="Business category (e.g. 'dentist', 'clothing store', 'real estate')"),
    count: int = typer.Option(50, "--count", "-n", help="Target number of leads to collect per provider"),
    sources: Optional[str] = typer.Option(None, "--sources", "-s", help="Comma-separated source providers (e.g. 'osm,geoapify')"),
):
    """Discover leads from multi-source providers and merge into the database."""
    setup_logging()
    init_db()

    source_list = [s.strip().lower() for s in sources.split(",")] if sources else None

    console.print(
        f"\n[bold green]Searching for {category} in {city}, {country}[/bold green]\n"
        f"Sources: [cyan]{', '.join(source_list) if source_list else 'osm, geoapify'}[/cyan] | "
        f"Requesting up to {count} leads per source\n"
    )

    try:
        res = run_scrape_pipeline(
            country=country,
            city=city,
            category=category,
            count=count,
            sources=source_list,
        )

        table = Table(title="Scrape Summary")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta", justify="right")

        table.add_row("Query", res.query)
        table.add_row("Sources used", ", ".join(res.sources_used))
        table.add_row("", "")

        table.add_row("OSM found", str(res.osm_count))
        table.add_row("Geoapify found", str(res.geoapify_count))
        table.add_row("Merged unique", str(res.total_found))
        table.add_row("", "")
        table.add_row("New leads saved", f"[green]{res.new_count}[/green]")
        table.add_row("Duplicates skipped", f"[yellow]{res.duplicate_count}[/yellow]")
        table.add_row("Errors", f"[red]{res.error_count}[/red]" if res.error_count else "0")
        table.add_row("", "")

        phone_fill = f"{res.coverage.phone_fill_rate:.0%}" if res.coverage.phone_fill_rate is not None else "N/A"
        web_fill = f"{res.coverage.website_fill_rate:.0%}" if res.coverage.website_fill_rate is not None else "N/A"
        table.add_row("Phone fill rate", phone_fill)
        table.add_row("Website fill rate", web_fill)
        table.add_row("Zero web presence", str(res.coverage.zero_web_presence_count))
        table.add_row("Contactable", f"[green]{res.coverage.contactable_count}[/green]")
        table.add_row("Needs manual lookup", f"[yellow]{res.coverage.needs_manual_lookup_count}[/yellow]")

        console.print(table)
        console.print(f"\nLog: [dim]logs/app.log[/dim]")

    except Exception as exc:
        console.print(f"\n[bold red]Scrape failed:[/bold red] {exc}")
        logger.error("Scrape command failed: %s", exc, exc_info=True)
        raise typer.Exit(code=1)


@app.command()
def analyze(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max number of leads to analyze"),
    city: Optional[str] = typer.Option(None, "--city", "-c", help="Filter by city name"),
    category: Optional[str] = typer.Option(None, "--category", "-k", help="Filter by business category"),
    reanalyze_all: bool = typer.Option(False, "--all", "-a", help="Re-analyze all leads, including previously analyzed"),
    batch_size: int = typer.Option(20, "--batch-size", "-b", help="Batch size for incremental DB commits"),
):
    """Crawl lead websites, extract contacts, performance signals, match canonical services, and compute scores."""
    setup_logging()
    init_db()

    console.print("\n[bold cyan]Running Phase 2 & 3 Lead Analysis & Web Crawling...[/bold cyan]\n")

    try:
        summary = run_analyze_pipeline(
            limit=limit,
            city=city,
            category=category,
            reanalyze_all=reanalyze_all,
            batch_size=batch_size,
        )

        table = Table(title="Analysis & Scoring Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count / Value", style="magenta", justify="right")

        table.add_row("Total leads analyzed", str(summary.total_analyzed))
        if summary.failed_analyses:
            table.add_row("Failed analyses", f"[red]{summary.failed_analyses}[/red]")
        table.add_row("HOT priority (Score >= 60)", f"[bold red]{summary.hot_count}[/bold red]")
        table.add_row("WARM priority (Score 30-59)", f"[bold yellow]{summary.warm_count}[/bold yellow]")
        table.add_row("COLD priority (Score < 30)", f"[bold blue]{summary.cold_count}[/bold blue]")
        table.add_row("", "")
        table.add_row("Actionable (Has Phone/Email)", f"[bold green]{summary.actionable_count}[/bold green]")
        table.add_row("Needs Manual Lookup", f"[yellow]{summary.needs_manual_lookup_count}[/yellow]")
        table.add_row("Flipped to contactable via crawl", f"[green]{summary.flipped_to_contactable}[/green]")
        table.add_row("", "")

        for srv, cnt in sorted(summary.service_breakdown.items(), key=lambda x: -x[1]):
            table.add_row(f"Service: {srv}", str(cnt))

        console.print(table)
        console.print(f"\nLog: [dim]logs/app.log[/dim]")

    except Exception as exc:
        console.print(f"\n[bold red]Analysis failed:[/bold red] {exc}")
        logger.error("Analyze command failed: %s", exc, exc_info=True)
        raise typer.Exit(code=1)


@app.command()
def export(
    out: str = typer.Option("data/export.csv", "--out", "-o", help="Output file path (.csv or .xlsx)"),
    format: str = typer.Option("csv", "--format", "-f", help="Export format: 'csv' or 'xlsx'"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Filter by priority (HOT, WARM, COLD)"),
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Filter by exact matched service name"),
    category: Optional[str] = typer.Option(None, "--category", "-k", help="Filter by business category / industry (e.g. dentist, real estate)"),
    industry: Optional[str] = typer.Option(None, "--industry", help="Alias for --category"),
    city: Optional[str] = typer.Option(None, "--city", "-c", help="Filter by city (case-insensitive)"),
    country: Optional[str] = typer.Option(None, "--country", "-C", help="Filter by country code or name"),
    min_score: Optional[int] = typer.Option(None, "--min-score", "-m", help="Filter by minimum score (0-100)"),
    has_email: Optional[bool] = typer.Option(None, "--has-email", help="Require email presence"),
    has_phone: Optional[bool] = typer.Option(None, "--has-phone", help="Require phone presence"),
    no_website: Optional[bool] = typer.Option(None, "--no-website", help="Filter for businesses without a website"),
    contactable: Optional[bool] = typer.Option(None, "--contactable/--needs-manual-lookup", help="Filter by contactable status"),
    discovery_source: Optional[str] = typer.Option(None, "--source", help="Filter by discovery provider (e.g. osm, geoapify)"),
):
    """Export filtered leads to CSV or Excel with combined AND logic."""
    setup_logging()
    init_db()

    effective_category = category or industry
    console.print(f"\n[bold cyan]Exporting leads to {out}...[/bold cyan]\n")

    try:
        df = LeadExporter.export_leads(
            output_path=out,
            format=format,
            priority=priority,
            service=service,
            category=effective_category,
            city=city,
            country=country,
            min_score=min_score,
            has_email=has_email,
            has_phone=has_phone,
            no_website=no_website,
            contactable=contactable,
            discovery_source=discovery_source,
        )

        table = Table(title="Export Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta", justify="right")

        table.add_row("Exported File", str(out))
        table.add_row("Format", format.upper())
        table.add_row("Total Leads Exported", f"[bold green]{len(df)}[/bold green]")
        if priority:
            table.add_row("Priority Filter", priority.upper())
        if service:
            table.add_row("Service Filter", service)
        if effective_category:
            table.add_row("Category / Industry Filter", effective_category)
        if city:
            table.add_row("City Filter", city)
        if country:
            table.add_row("Country Filter", country)
        if min_score is not None:
            table.add_row("Min Score Filter", str(min_score))
        if contactable is not None:
            table.add_row("Contactable Filter", str(contactable))

        console.print(table)
        console.print(f"\nSaved {len(df)} leads to [bold green]{out}[/bold green]\n")

    except Exception as exc:
        console.print(f"\n[bold red]Export failed:[/bold red] {exc}")
        logger.error("Export command failed: %s", exc, exc_info=True)
        raise typer.Exit(code=1)


@app.command()
def run(
    country: str = typer.Option(..., "--country", "-C", help="2-letter ISO country code (e.g. PK, DE, GB, US, AE)"),
    city: str = typer.Option(..., "--city", "-c", help="City name to search (e.g. Karachi, Berlin, London, Dubai)"),
    category: str = typer.Option(..., "--category", "-k", help="Business category (e.g. 'dentist', 'clothing store', 'real estate')"),
    count: int = typer.Option(20, "--count", "-n", help="Target number of leads to collect per provider"),
    batch_size: int = typer.Option(20, "--batch-size", "-b", help="Batch size for crawler enrichment"),
    export_out: Optional[str] = typer.Option("data/export.csv", "--export-out", "-o", help="Path to export final qualified leads"),
    export_format: str = typer.Option("csv", "--export-format", "-f", help="Export format: csv or xlsx"),
    no_export: bool = typer.Option(False, "--no-export", help="Skip file export step and only save to database"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p", help="Export filter: priority (HOT/WARM/COLD)"),
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Export filter: service name"),
    min_score: Optional[int] = typer.Option(None, "--min-score", "-m", help="Export filter: min score"),
    contactable: Optional[bool] = typer.Option(None, "--contactable/--needs-manual-lookup", help="Export filter: contactable"),
):
    """
    Run full end-to-end pipeline in one call:
    1. Multi-source discovery (OSM + Geoapify)
    2. Batch web crawling, performance signals, service matching, and opportunity scoring
    3. Multi-criteria export to CSV or XLSX (or skip export with --no-export)
    """
    setup_logging()
    init_db()

    console.print(f"\n[bold green]================================================================[/bold green]")
    console.print(f"[bold green]Starting End-to-End Pipeline for '{category}' in {city}, {country}[/bold green]")
    console.print(f"[bold green]================================================================[/bold green]\n")

    # Step 1: Scrape & Merge
    console.print("[bold cyan]Step 1/3: Multi-Source Discovery (OSM + Geoapify)...[/bold cyan]")
    scrape_res = run_scrape_pipeline(
        country=country,
        city=city,
        category=category,
        count=count,
    )
    console.print(f"-> Discovered {scrape_res.new_count} new leads ({scrape_res.duplicate_count} duplicates skipped).\n")

    # Step 2: Batch Analyze & Enrich
    console.print(f"[bold cyan]Step 2/3: Batch Web Crawling & Service Scoring (batch_size={batch_size})...[/bold cyan]")
    analyze_summary = run_analyze_pipeline(
        city=city,
        category=category,
        reanalyze_all=True,
        batch_size=batch_size,
    )
    console.print(f"-> Analyzed {analyze_summary.total_analyzed} leads (Actionable: {analyze_summary.actionable_count}, Needs Lookup: {analyze_summary.needs_manual_lookup_count}).\n")

    # Step 3: Export scoped to category, city, country, and optional filters (unless --no-export is set)
    df = None
    if not no_export and export_out:
        console.print(f"[bold cyan]Step 3/3: Exporting Filtered Leads to {export_out}...[/bold cyan]")
        df = LeadExporter.export_leads(
            output_path=export_out,
            format=export_format,
            priority=priority,
            service=service,
            category=category,
            city=city,
            country=country,
            min_score=min_score,
            contactable=contactable,
        )
        console.print(f"-> Successfully exported {len(df)} leads to [bold green]{export_out}[/bold green].\n")
    else:
        console.print("[bold yellow]Step 3/3: File export skipped (--no-export enabled). All leads are saved in database.[/bold yellow]\n")

    # End-of-Run Summary Table
    table = Table(title="End-to-End Run Summary")
    table.add_column("Pipeline Phase", style="cyan")
    table.add_column("Key Metric", style="yellow")
    table.add_column("Value", style="magenta", justify="right")

    table.add_row("1. Discovery", "New Leads Discovered", f"[green]{scrape_res.new_count}[/green]")
    table.add_row("1. Discovery", "Duplicates Skipped", str(scrape_res.duplicate_count))
    table.add_row("1. Discovery", "Phone Fill Rate", f"{scrape_res.coverage.phone_fill_rate:.0%}" if scrape_res.coverage.phone_fill_rate else "N/A")
    table.add_row("1. Discovery", "Website Fill Rate", f"{scrape_res.coverage.website_fill_rate:.0%}" if scrape_res.coverage.website_fill_rate else "N/A")
    table.add_row("", "", "")
    table.add_row("2. Enrichment", "Total Analyzed", str(analyze_summary.total_analyzed))
    table.add_row("2. Enrichment", "Actionable Leads", f"[green]{analyze_summary.actionable_count}[/green]")
    table.add_row("2. Enrichment", "Needs Manual Lookup", f"[yellow]{analyze_summary.needs_manual_lookup_count}[/yellow]")
    table.add_row("2. Enrichment", "WARM Priority Leads", str(analyze_summary.warm_count))
    table.add_row("2. Enrichment", "COLD Priority Leads", str(analyze_summary.cold_count))
    table.add_row("", "", "")
    if not no_export and export_out and df is not None:
        table.add_row("3. Export", "Export File", str(export_out))
        table.add_row("3. Export", "Exported Row Count", f"[bold green]{len(df)}[/bold green]")
    else:
        table.add_row("3. Export", "File Generation", "[yellow]Skipped (Database Only)[/yellow]")

    console.print(table)
    console.print(f"\n[bold green]Pipeline finished successfully.[/bold green] Log: [dim]logs/app.log[/dim]")


@app.command()
def info():
    """Display database statistics, lead breakdown, and fill rates."""
    setup_logging()
    init_db()

    with get_session() as session:
        leads = session.query(Lead).all()
        total = len(leads)

        if not total:
            console.print("[yellow]Database is currently empty. Run 'main.py scrape' first.[/yellow]")
            return

        with_phone = sum(1 for l in leads if l.phone)
        with_email = sum(1 for l in leads if l.email)
        with_web = sum(1 for l in leads if l.website)
        contactable = sum(1 for l in leads if l.contactable)
        hot = sum(1 for l in leads if l.priority == "HOT")
        warm = sum(1 for l in leads if l.priority == "WARM")
        cold = sum(1 for l in leads if l.priority == "COLD")

        table = Table(title="Database Health & Lead Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="magenta", justify="right")
        table.add_column("Percentage", style="green", justify="right")

        table.add_row("Total Leads", str(total), "100%")
        table.add_row("Phone Available", str(with_phone), f"{with_phone/total:.1%}")
        table.add_row("Email Available", str(with_email), f"{with_email/total:.1%}")
        table.add_row("Website Available", str(with_web), f"{with_web/total:.1%}")
        table.add_row("Contactable (Ready)", str(contactable), f"{contactable/total:.1%}")
        table.add_row("Needs Manual Lookup", str(total - contactable), f"{(total - contactable)/total:.1%}")
        table.add_row("", "", "")
        table.add_row("HOT Priority", str(hot), f"{hot/total:.1%}")
        table.add_row("WARM Priority", str(warm), f"{warm/total:.1%}")
        table.add_row("COLD Priority", str(cold), f"{cold/total:.1%}")

        console.print(table)


if __name__ == "__main__":
    app()
