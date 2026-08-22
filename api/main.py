"""
FastAPI Backend API for Lead Scraper & Agency Qualification Engine (Phase 4).

Provides RESTful endpoints for:
1. Triggering background scrape + crawl + scoring jobs (/leads/search)
2. Polling background job status (/leads/jobs/{job_id})
3. Querying paginated leads with live multi-criteria filters (/leads)
4. Streaming file exports with dynamic descriptive filenames (/leads/export)
5. Fetching single lead details (/leads/{id})
6. Real-time database metrics & dropdown options (/stats)

NOTE:
This API uses a single-process in-memory job store (dict).
Job history resets on server restart. Run as a single worker process.
"""

import io
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config.settings import setup_logging, normalize_category
from db.models import Lead, ScrapeLog
from db.session import get_session, init_db
from export.exporter import LeadExporter
from pipeline.analyzer_orchestrator import run_analyze_pipeline
from pipeline.orchestrator import run_scrape_pipeline

setup_logging()
init_db()

logger = logging.getLogger("api.main")

app = FastAPI(
    title="Lead Scraper & Qualification API",
    description=(
        "REST API layer for multi-source business lead discovery, deep website auditing, "
        "and agency qualification. Powered by MySQL storage."
    ),
    version="1.0.0",
    debug=False,
)

# Enable CORS for localhost React frontend (e.g. Vite on 5173, Next.js on 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Safely log internal server errors without leaking file paths or DB schemas in HTTP responses."""
    logger.error(f"Unhandled error processing request {request.method} {request.url.path}: {exc}", exc_info=True)
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please check server logs for details."},
    )


# -----------------------------------------------------------------------------
# In-Memory Job Storage (Single-User Internal Tool)
# -----------------------------------------------------------------------------
# Job status history is kept in memory. Resets on server restart.
# Run FastAPI with a single worker process (default in uvicorn).
jobs: dict[str, dict[str, Any]] = {}


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def generate_export_filename(
    format: str,
    city: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    service: Optional[str] = None,
    contactable: Optional[bool] = None,
) -> str:
    """Generate a descriptive, collision-resistant filename with active filters and timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    parts = []

    if city and city.strip():
        clean_city = re.sub(r"[^\w\-]", "", city.strip())
        if clean_city:
            parts.append(clean_city)
    if category and category.strip() and category.upper() != "ALL":
        clean_cat = re.sub(r"[^\w\-]", "_", category.strip())
        if clean_cat:
            parts.append(clean_cat)
    if priority and priority.strip() and priority.upper() != "ALL":
        parts.append(priority.strip().upper())
    if service and service.strip() and service.upper() != "ALL":
        clean_svc = re.sub(r"[^\w\-]", "_", service.strip())
        if clean_svc:
            parts.append(clean_svc)
    if contactable is True:
        parts.append("actionable")
    elif contactable is False:
        parts.append("lookup")

    if not parts:
        filter_slug = "all"
    else:
        filter_slug = "_".join(parts)

    return f"leads_export_{filter_slug}_{timestamp}.{format}"


# -----------------------------------------------------------------------------
# Pydantic Request & Response Models
# -----------------------------------------------------------------------------

class SearchRequest(BaseModel):
    country: str = Field(default="US", description="2-letter ISO country code (e.g. US, CA, DE, GB, AE, PK)")
    city: str = Field(..., min_length=1, description="Target city name (e.g. Miami, Toronto, Berlin)")
    category: str = Field(..., min_length=1, description="Business category or industry (e.g. dentist, real estate)")
    count: int = Field(default=20, ge=1, le=100, description="Total unique leads to scrape (1-100)")


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(description="pending, running, complete, or failed")
    progress: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    count: Optional[int] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class LeadResponse(BaseModel):
    id: int
    business_name: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    status: str
    score: Optional[int] = None
    priority: Optional[str] = None
    contactable: bool
    lead_status: Optional[str] = None
    matched_services: list[str] = []
    reason: Optional[str] = None
    response_time_ms: Optional[float] = None
    page_size_kb: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LeadDetailResponse(BaseModel):
    id: int
    business_name: Optional[str] = None
    category: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    source_url: Optional[str] = None
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    linkedin: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    status: str
    score: Optional[int] = None
    priority: Optional[str] = None
    contactable: bool
    lead_status: Optional[str] = None
    matched_services: list[str] = []
    reason: Optional[str] = None
    response_time_ms: Optional[float] = None
    page_size_kb: Optional[float] = None
    discovery_sources: list[str] = []
    dedup_hash: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PaginatedLeadsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    leads: list[LeadResponse]


class StatsResponse(BaseModel):
    total_leads: int
    hot_count: int
    warm_count: int
    cold_count: int
    contactable_count: int
    needs_manual_lookup_count: int
    phone_fill_rate: float
    email_fill_rate: float
    categories: list[str]
    cities: list[str]


# -----------------------------------------------------------------------------
# Background Task Runner
# -----------------------------------------------------------------------------

def run_search_job_task(job_id: str, country: str, city: str, category: str, count: int) -> None:
    """
    Executes the discovery and web analysis pipeline in the background.
    """
    jobs[job_id]["status"] = "running"
    jobs[job_id]["progress"] = f"Step 1/2: Scraping '{category}' in {city}, {country} (OSM + Geoapify)"
    logger.info(f"Background Job [{job_id}] started for {category} in {city}, {country}")

    try:
        # Step 1: Discovery (enforcing total unique count cap)
        scrape_res = run_scrape_pipeline(
            country=country,
            city=city,
            category=category,
            count=count,
        )

        # Step 2: Web Crawling & Service Scoring
        jobs[job_id]["progress"] = "Step 2/2: Crawling websites, auditing SEO & performance, matching services"
        analyze_res = run_analyze_pipeline(
            city=city,
            category=category,
            reanalyze_all=False,
            batch_size=20,
        )

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = "Complete"
        jobs[job_id]["result"] = {
            "new_leads_saved": scrape_res.new_count,
            "duplicates_skipped": scrape_res.duplicate_count,
            "total_analyzed": analyze_res.total_analyzed,
            "actionable_leads": analyze_res.actionable_count,
            "needs_manual_lookup": analyze_res.needs_manual_lookup_count,
            "hot_leads": analyze_res.hot_count,
            "warm_leads": analyze_res.warm_count,
            "cold_leads": analyze_res.cold_count,
        }
        jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Background Job [{job_id}] completed successfully.")

    except Exception as exc:
        logger.error(f"Background Job [{job_id}] failed: {exc}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = "Failed"
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@app.post(
    "/leads/search",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger new lead discovery and analysis",
)
def search_leads(
    req: SearchRequest,
    background_tasks: BackgroundTasks,
) -> JobCreateResponse:
    """
    Triggers lead discovery and web crawling as a background task.
    Rejects request with 409 Conflict if another job is currently running.
    """
    # Check if a job is already actively running
    for j_id, j_data in jobs.items():
        if j_data.get("status") == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A scrape and analysis job is already in progress. Please wait for it to complete.",
            )

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": "Queued",
        "country": req.country,
        "city": req.city,
        "category": req.category,
        "count": req.count,
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }

    background_tasks.add_task(
        run_search_job_task,
        job_id=job_id,
        country=req.country.strip(),
        city=req.city.strip(),
        category=req.category.strip(),
        count=req.count,
    )

    return JobCreateResponse(
        job_id=job_id,
        status="pending",
        message=f"Search job created for '{req.category}' in {req.city}, {req.country}.",
    )


@app.get(
    "/leads/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get background search job status",
)
def get_job_status(job_id: str) -> JobStatusResponse:
    """
    Poll the execution status and results of a background search job.
    """
    if job_id not in jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobStatusResponse(**jobs[job_id])


@app.get(
    "/leads/export",
    summary="Download filtered leads spreadsheet (CSV or XLSX) with dynamic descriptive filename",
)
def export_leads_file(
    format: str = Query("csv", pattern="^(csv|xlsx)$", description="File format: csv or xlsx"),
    priority: Optional[str] = Query(None, description="HOT, WARM, or COLD"),
    service: Optional[str] = Query(None, description="Canonical service name"),
    city: Optional[str] = Query(None, description="City name"),
    category: Optional[str] = Query(None, description="Category / Industry"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum opportunity score"),
    has_email: Optional[bool] = Query(None, description="Has email"),
    has_phone: Optional[bool] = Query(None, description="Has phone"),
    no_website: Optional[bool] = Query(None, description="No website"),
    contactable: Optional[bool] = Query(None, description="Contactable"),
) -> Response:
    """
    Applies filters and streams a downloadable CSV or Excel (.xlsx) file with a descriptive, collision-resistant filename.
    """
    filename = generate_export_filename(
        format=format,
        city=city,
        category=category,
        priority=priority,
        service=service,
        contactable=contactable,
    )

    temp_path = Path("data") / f".api_export_{uuid.uuid4().hex}.{format}"
    try:
        LeadExporter.export_leads(
            output_path=str(temp_path),
            format=format,
            priority=priority,
            service=service,
            category=category,
            city=city,
            min_score=min_score,
            contactable=contactable,
            has_email=has_email,
            has_phone=has_phone,
            no_website=no_website,
        )

        if not temp_path.exists():
            raise HTTPException(status_code=500, detail="Export file generation failed.")

        file_bytes = temp_path.read_bytes()
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

    if format == "xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media_type = "text/csv; charset=utf-8"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get(
    "/leads",
    response_model=PaginatedLeadsResponse,
    summary="List and filter leads with pagination",
)
def list_leads(
    priority: Optional[str] = Query(None, description="HOT, WARM, or COLD"),
    service: Optional[str] = Query(None, description="Canonical service name (e.g. SEO, Google Ads)"),
    city: Optional[str] = Query(None, description="City name filter"),
    category: Optional[str] = Query(None, description="Category / Industry filter"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum opportunity score"),
    has_email: Optional[bool] = Query(None, description="Filter leads with an email"),
    has_phone: Optional[bool] = Query(None, description="Filter leads with a phone"),
    no_website: Optional[bool] = Query(None, description="Filter leads with no website"),
    contactable: Optional[bool] = Query(None, description="Filter contactable leads"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Leads per page"),
) -> PaginatedLeadsResponse:
    """
    Query leads from MySQL using the exact export filter engine, with pagination.
    """
    temp_path = Path("data") / f".api_filter_{uuid.uuid4().hex}.csv"
    try:
        df = LeadExporter.export_leads(
            output_path=str(temp_path),
            format="csv",
            priority=priority,
            service=service,
            category=category,
            city=city,
            min_score=min_score,
            contactable=contactable,
            has_email=has_email,
            has_phone=has_phone,
            no_website=no_website,
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

    total = len(df)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    page_df = df.iloc[start_idx:end_idx] if total else pd.DataFrame()

    leads_list: list[LeadResponse] = []
    for _, row in page_df.iterrows():
        # Parse matched_services string into list
        svcs = []
        raw_svcs = row.get("matched_services")
        if pd.notna(raw_svcs) and raw_svcs:
            if isinstance(raw_svcs, list):
                svcs = raw_svcs
            elif isinstance(raw_svcs, str):
                try:
                    parsed = json.loads(raw_svcs)
                    if isinstance(parsed, list):
                        svcs = parsed
                except Exception:
                    svcs = [s.strip() for s in str(raw_svcs).split(",") if s.strip()]

        resp_time = row.get("response_time_ms")
        resp_time_val = float(resp_time) if pd.notna(resp_time) and str(resp_time).strip() != "" else None

        page_size_kb = row.get("page_size_kb")
        page_size_val = float(page_size_kb) if pd.notna(page_size_kb) and str(page_size_kb).strip() != "" else None

        score_val = int(row.get("score")) if pd.notna(row.get("score")) and str(row.get("score")).strip() != "" else None

        leads_list.append(
            LeadResponse(
                id=int(row["id"]),
                business_name=str(row["business_name"]) if pd.notna(row.get("business_name")) else None,
                category=str(row["category"]) if pd.notna(row.get("category")) else None,
                website=str(row["website"]) if pd.notna(row.get("website")) and row.get("website") else None,
                phone=str(row["phone"]) if pd.notna(row.get("phone")) and row.get("phone") else None,
                email=str(row["email"]) if pd.notna(row.get("email")) and row.get("email") else None,
                address=str(row["address"]) if pd.notna(row.get("address")) and row.get("address") else None,
                city=str(row["city"]) if pd.notna(row.get("city")) else None,
                country=str(row["country"]) if pd.notna(row.get("country")) else None,
                status=str(row.get("status", "analyzed")),
                score=score_val,
                priority=str(row["priority"]) if pd.notna(row.get("priority")) else None,
                contactable=bool(row.get("contactable", False)),
                lead_status=str(row["lead_status"]) if pd.notna(row.get("lead_status")) else None,
                matched_services=svcs,
                reason=str(row["reason"]) if pd.notna(row.get("reason")) else None,
                response_time_ms=resp_time_val,
                page_size_kb=page_size_val,
                created_at=str(row["created_at"]) if pd.notna(row.get("created_at")) else None,
                updated_at=str(row["updated_at"]) if pd.notna(row.get("updated_at")) else None,
            )
        )

    return PaginatedLeadsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        leads=leads_list,
    )


@app.get(
    "/leads/{lead_id}",
    response_model=LeadDetailResponse,
    summary="Get single lead details",
)
def get_lead_by_id(lead_id: int) -> LeadDetailResponse:
    """
    Fetch comprehensive details for a specific lead by its database ID.
    """
    with get_session() as session:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if lead is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead with id {lead_id} not found.",
            )

        # Parse JSON fields
        svcs = lead.matched_services
        if isinstance(svcs, str):
            try:
                svcs = json.loads(svcs)
            except Exception:
                svcs = []
        elif not isinstance(svcs, list):
            svcs = []

        sources = lead.discovery_sources
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except Exception:
                sources = []
        elif not isinstance(sources, list):
            sources = []

        return LeadDetailResponse(
            id=lead.id,
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
            contactable=lead.contactable,
            lead_status="actionable" if lead.contactable else "needs_manual_lookup",
            matched_services=svcs,
            reason=lead.reason,
            response_time_ms=lead.response_time_ms,
            page_size_kb=lead.page_size_kb,
            discovery_sources=sources,
            dedup_hash=lead.dedup_hash,
            created_at=lead.created_at.isoformat() if lead.created_at else None,
            updated_at=lead.updated_at.isoformat() if lead.updated_at else None,
        )


@app.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get overall database metrics and dropdown lists",
)
def get_stats() -> StatsResponse:
    """
    Returns real-time totals, priority distributions, contact coverage,
    and distinct canonical lists of categories and cities from MySQL.
    """
    with get_session() as session:
        leads = session.query(Lead).all()
        total = len(leads)

        if not total:
            return StatsResponse(
                total_leads=0,
                hot_count=0,
                warm_count=0,
                cold_count=0,
                contactable_count=0,
                needs_manual_lookup_count=0,
                phone_fill_rate=0.0,
                email_fill_rate=0.0,
                categories=[],
                cities=[],
            )

        hot = sum(1 for l in leads if l.priority == "HOT")
        warm = sum(1 for l in leads if l.priority == "WARM")
        cold = sum(1 for l in leads if l.priority == "COLD")
        contactable = sum(1 for l in leads if l.contactable)
        needs_manual = total - contactable
        phone_count = sum(1 for l in leads if l.phone and l.phone.strip())
        email_count = sum(1 for l in leads if l.email and l.email.strip())

        # Normalize and deduplicate category names
        raw_cats = [normalize_category(l.category) for l in leads if l.category and l.category.strip()]
        categories = sorted(list(set(c for c in raw_cats if c)))
        cities = sorted(list(set(l.city for l in leads if l.city and l.city.strip())))

        return StatsResponse(
            total_leads=total,
            hot_count=hot,
            warm_count=warm,
            cold_count=cold,
            contactable_count=contactable,
            needs_manual_lookup_count=needs_manual,
            phone_fill_rate=round((phone_count / total) * 100, 1),
            email_fill_rate=round((email_count / total) * 100, 1),
            categories=categories,
            cities=cities,
        )
