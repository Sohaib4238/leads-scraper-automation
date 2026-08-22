"""
Streamlit Web Dashboard for Lead Scraper & Agency Qualification Engine.

Provides:
1. Search & Discovery: Dynamic database-backed Category dropdown, Country, City, Lead Count with real-time pipeline execution.
2. Filter Sidebar: Multi-criteria live filtering (Priority, Service, Category dropdown, City, Min Score, Contactable, Email, Phone, Website).
3. Database KPIs: Real-time stats bar with sentence-case card titles.
4. Direct Browser Exports: Download filtered leads as CSV or Excel (XLSX).
5. Clean, flat design system with colored Priority badges in the data table.
"""

import io
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from config.settings import setup_logging
from db.session import init_db, get_session
from db.models import Lead
from pipeline.orchestrator import run_scrape_pipeline
from pipeline.analyzer_orchestrator import run_analyze_pipeline
from export.exporter import LeadExporter
from matcher.service_matcher import CANONICAL_SERVICES

# Page Configuration
st.set_page_config(
    page_title="Lead Scraper & Qualification Dashboard",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Flat, clean, non-AI styling injection
CUSTOM_CSS = """
<style>
/* Global Clean Sans-Serif Font & Neutral Canvas */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #0f172a;
}

/* App Background & Container */
.stApp {
    background-color: #f8fafc;
}

.main .block-container {
    padding-top: 1.75rem;
    padding-bottom: 3rem;
    max-width: 1380px;
}

/* Typography Hierarchy */
h1, h2, h3, h4 {
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    color: #0f172a !important;
}

h1 {
    font-size: 1.65rem !important;
    margin-bottom: 0.25rem !important;
}

p, span, label {
    font-size: 0.92rem;
    color: #334155;
}

/* Clean Header Section */
.header-container {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #e2e8f0;
}

.header-subtitle {
    font-size: 0.95rem;
    color: #64748b;
    margin: 0;
}

/* KPI Metric Cards - Flat, Subtle 1px Border, No Shadow, Sentence Case */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.stat-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 1rem 1.25rem;
}

.stat-card-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #64748b;
    margin-bottom: 0.35rem;
}

.stat-card-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.1;
}

.stat-card-subtext {
    font-size: 0.8rem;
    color: #64748b;
    margin-top: 0.25rem;
}

/* Search Box Container */
.search-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
}

.section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #0f172a;
    margin-bottom: 0.85rem;
}

/* Flat Accent Buttons */
.stButton > button, div.stDownloadButton > button {
    background-color: #0f172a !important;
    color: #ffffff !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    border: 1px solid #0f172a !important;
    border-radius: 5px !important;
    padding: 0.5rem 1rem !important;
    box-shadow: none !important;
    transition: background-color 0.15s ease-in-out;
}

.stButton > button:hover, div.stDownloadButton > button:hover {
    background-color: #1e293b !important;
    border-color: #1e293b !important;
}

/* Secondary Button Style */
div.stDownloadButton > button {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
}

div.stDownloadButton > button:hover {
    background-color: #f1f5f9 !important;
    border-color: #94a3b8 !important;
}

/* Form Inputs & Selects */
div[data-baseweb="input"], div[data-baseweb="select"] {
    border-radius: 5px !important;
}

/* Sidebar Clean Polish */
section[data-testid="stSidebar"] {
    background-color: #ffffff;
    border-right: 1px solid #e2e8f0;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 2rem;
}

/* Hide Streamlit default decoration & footer */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def load_db_kpis() -> dict:
    """Fetch live counts and metrics directly from the SQLite database."""
    setup_logging()
    init_db()

    with get_session() as session:
        leads = session.query(Lead).all()
        total = len(leads)
        if not total:
            return {
                "total": 0, "hot": 0, "warm": 0, "cold": 0,
                "contactable": 0, "needs_manual": 0,
                "phone_fill": 0.0, "email_fill": 0.0,
            }

        hot = sum(1 for l in leads if l.priority == "HOT")
        warm = sum(1 for l in leads if l.priority == "WARM")
        cold = sum(1 for l in leads if l.priority == "COLD")
        contactable = sum(1 for l in leads if l.contactable)
        needs_manual = total - contactable
        phone_count = sum(1 for l in leads if l.phone and l.phone.strip())
        email_count = sum(1 for l in leads if l.email and l.email.strip())

        return {
            "total": total,
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "contactable": contactable,
            "needs_manual": needs_manual,
            "phone_fill": (phone_count / total) * 100,
            "email_fill": (email_count / total) * 100,
        }


def get_distinct_categories() -> list[str]:
    """Query DISTINCT category values from the database."""
    with get_session() as session:
        raw_cats = [r[0] for r in session.query(Lead.category).distinct().all() if r[0] and r[0].strip()]
    return sorted(list(set(raw_cats)))


def highlight_priority(val: str) -> str:
    """Return flat colored pill styling for Priority column cells."""
    if val == "HOT":
        return "background-color: #fee2e2; color: #991b1b; font-weight: 600;"
    elif val == "WARM":
        return "background-color: #fef3c7; color: #92400e; font-weight: 600;"
    elif val == "COLD":
        return "background-color: #f1f5f9; color: #475569; font-weight: 600;"
    return ""


# -----------------------------------------------------------------------------
# Header & KPI Stats Bar (Sentence Case)
# -----------------------------------------------------------------------------

st.markdown("""
<div class="header-container">
    <h1>Lead Scraper & Qualification Dashboard</h1>
    <p class="header-subtitle">Multi-source B2B lead discovery, technical website auditing, and agency qualification.</p>
</div>
""", unsafe_allow_html=True)

# Fetch real-time database KPIs
kpis = load_db_kpis()
db_categories = get_distinct_categories()

st.markdown(f"""
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-card-title">Total database leads</div>
        <div class="stat-card-value">{kpis['total']}</div>
        <div class="stat-card-subtext">Persisted in MySQL database</div>
    </div>
    <div class="stat-card">
        <div class="stat-card-title">Actionable leads</div>
        <div class="stat-card-value">{kpis['contactable']}</div>
        <div class="stat-card-subtext">{kpis['contactable'] / kpis['total'] * 100 if kpis['total'] else 0:.1f}% ready to contact</div>
    </div>
    <div class="stat-card">
        <div class="stat-card-title">Warm & hot opportunities</div>
        <div class="stat-card-value">{kpis['hot'] + kpis['warm']}</div>
        <div class="stat-card-subtext">{kpis['hot']} HOT | {kpis['warm']} WARM</div>
    </div>
    <div class="stat-card">
        <div class="stat-card-title">Contact coverage</div>
        <div class="stat-card-value">{kpis['phone_fill']:.0f}%</div>
        <div class="stat-card-subtext">Phone: {kpis['phone_fill']:.0f}% | Email: {kpis['email_fill']:.0f}%</div>
    </div>
</div>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Search & Pipeline Execution Section
# -----------------------------------------------------------------------------

with st.container():
    st.markdown('<div class="search-card"><div class="section-title">Discover & Analyze New Leads</div>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns([1.5, 2.5, 3.5, 1.5])
    
    with col1:
        country_input = st.selectbox(
            "Country",
            options=["US", "CA", "DE", "GB", "AE", "PK"],
            index=0,
            help="2-letter ISO country code (e.g. US, CA, DE)",
        )
        
    with col2:
        city_input = st.text_input(
            "City",
            value="Miami",
            placeholder="e.g. Miami, Toronto, Berlin",
        )
        
    with col3:
        search_category_options = ["All"] + db_categories if db_categories else ["All", "real estate", "dentist", "lawyer", "clothing store"]
        selected_search_cat = st.selectbox(
            "Category / Industry",
            options=search_category_options,
            index=1 if len(search_category_options) > 1 else 0,
            help="Select an existing category from database or choose All",
        )
        
    with col4:
        count_input = st.number_input(
            "Lead Count",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
        )

    search_clicked = st.button("Search & Analyze Leads", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Run Discovery & Crawling Pipeline on click
if search_clicked:
    target_cat = selected_search_cat if selected_search_cat != "All" else "real estate"
    if not city_input.strip():
        st.error("Please specify a city name.")
    else:
        status_box = st.status("Executing discovery & web analysis pipeline...", expanded=True)
        try:
            status_box.write(f"Step 1/2: Querying OpenStreetMap & Geoapify for '{target_cat}' in {city_input}, {country_input}...")
            scrape_res = run_scrape_pipeline(
                country=country_input.strip(),
                city=city_input.strip(),
                category=target_cat.strip(),
                count=int(count_input),
            )
            status_box.write(f"Discovery complete: Found {scrape_res.new_count} new leads ({scrape_res.duplicate_count} duplicates skipped).")

            status_box.write("Step 2/2: Crawling websites, auditing SEO & performance, matching services, and scoring leads...")
            analyze_summary = run_analyze_pipeline(
                city=city_input.strip(),
                category=target_cat.strip(),
                reanalyze_all=False,
                batch_size=20,
            )
            status_box.write(f"Analysis complete: {analyze_summary.total_analyzed} leads analyzed ({analyze_summary.actionable_count} actionable).")
            status_box.update(label="Pipeline finished successfully!", state="complete", expanded=False)
            st.rerun()

        except Exception as exc:
            status_box.update(label="Pipeline execution failed", state="error")
            st.error(f"Execution error: {exc}")


# -----------------------------------------------------------------------------
# Sidebar: Live Multi-Criteria Filters
# -----------------------------------------------------------------------------

st.sidebar.markdown("### Filter Database Leads")

# Priority Filter
priority_filter = st.sidebar.selectbox(
    "Priority Tier",
    options=["All", "HOT", "WARM", "COLD"],
    index=0,
)
selected_priority = None if priority_filter == "All" else priority_filter

# Service Filter
service_options = ["All"] + sorted(list(CANONICAL_SERVICES))
service_filter = st.sidebar.selectbox(
    "Matched Service",
    options=service_options,
    index=0,
)
selected_service = None if service_filter == "All" else service_filter

# Category Filter (Dynamic Dropdown)
sidebar_category_options = ["All"] + db_categories
category_filter = st.sidebar.selectbox(
    "Category / Industry",
    options=sidebar_category_options,
    index=0,
)
selected_category = None if category_filter == "All" else category_filter

# City Filter
city_filter = st.sidebar.text_input(
    "Filter by City",
    value="",
    placeholder="e.g. Miami, Berlin, Toronto",
)
selected_city = city_filter.strip() if city_filter.strip() else None

# Score Slider
min_score_filter = st.sidebar.slider(
    "Minimum Opportunity Score",
    min_value=0,
    max_value=100,
    value=0,
    step=5,
)
selected_min_score = min_score_filter if min_score_filter > 0 else None

# Contactability Status Filter
contactable_selection = st.sidebar.selectbox(
    "Contact Outreach Status",
    options=["All Leads", "Actionable (Phone or Email Available)", "Needs Manual Lookup"],
    index=0,
)
if contactable_selection == "Actionable (Phone or Email Available)":
    selected_contactable = True
elif contactable_selection == "Needs Manual Lookup":
    selected_contactable = False
else:
    selected_contactable = None

# Boolean Attribute Checkboxes
st.sidebar.markdown("---")
st.sidebar.markdown("**Additional Attributes**")
has_email_chk = st.sidebar.checkbox("Has verified email", value=False)
has_phone_chk = st.sidebar.checkbox("Has verified phone", value=False)
no_website_chk = st.sidebar.checkbox("No website (Web Dev prospect)", value=False)

selected_has_email = True if has_email_chk else None
selected_has_phone = True if has_phone_chk else None
selected_no_website = True if no_website_chk else None


# -----------------------------------------------------------------------------
# Query Filtered Leads via Exporter Logic
# -----------------------------------------------------------------------------

# We invoke LeadExporter directly to reuse 100% of the tested AND-logic filtering
temp_export_path = Path("data") / ".temp_ui_export.csv"
filtered_df = LeadExporter.export_leads(
    output_path=str(temp_export_path),
    format="csv",
    priority=selected_priority,
    service=selected_service,
    category=selected_category,
    city=selected_city,
    min_score=selected_min_score,
    contactable=selected_contactable,
    has_email=selected_has_email,
    has_phone=selected_has_phone,
    no_website=selected_no_website,
)

# Clean up temp file
if temp_export_path.exists():
    try:
        temp_export_path.unlink()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Results Table & Direct Browser Downloads
# -----------------------------------------------------------------------------

col_header, col_csv, col_xlsx = st.columns([6, 2, 2])

with col_header:
    st.markdown(f"### Filtered Results ({len(filtered_df)} leads found)")

# Generate byte payloads for direct downloads
csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    filtered_df.to_excel(writer, index=False)
excel_bytes = excel_buffer.getvalue()

with col_csv:
    st.download_button(
        label="Download as CSV",
        data=csv_bytes,
        file_name="filtered_leads.csv",
        mime="text/csv",
        use_container_width=True,
    )

with col_xlsx:
    st.download_button(
        label="Download as Excel",
        data=excel_bytes,
        file_name="filtered_leads.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

if filtered_df.empty:
    st.info("No leads match the current search or filter criteria. Try adjusting the sidebar filters or running a new search above.")
else:
    # Display table with curated columns and clean type conversions
    display_columns = [
        "id",
        "business_name",
        "category",
        "city",
        "country",
        "phone",
        "email",
        "website",
        "score",
        "priority",
        "lead_status",
        "matched_services",
        "response_time_ms",
        "page_size_kb",
    ]
    available_cols = [c for c in display_columns if c in filtered_df.columns]
    df_to_display = filtered_df[available_cols].copy()

    # Clean numeric types for Arrow
    if "response_time_ms" in df_to_display.columns:
        df_to_display["response_time_ms"] = pd.to_numeric(df_to_display["response_time_ms"], errors="coerce")
    if "page_size_kb" in df_to_display.columns:
        df_to_display["page_size_kb"] = pd.to_numeric(df_to_display["page_size_kb"], errors="coerce")
    if "score" in df_to_display.columns:
        df_to_display["score"] = pd.to_numeric(df_to_display["score"], errors="coerce").fillna(0).astype(int)

    # Apply flat color badges to Priority column
    styled_df = df_to_display.style.map(highlight_priority, subset=["priority"])

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "business_name": st.column_config.TextColumn("Business Name", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "city": st.column_config.TextColumn("City", width="small"),
            "country": st.column_config.TextColumn("Country", width="small"),
            "phone": st.column_config.TextColumn("Phone", width="small"),
            "email": st.column_config.TextColumn("Email", width="medium"),
            "website": st.column_config.LinkColumn("Website", width="medium"),
            "score": st.column_config.NumberColumn("Score", width="small"),
            "priority": st.column_config.TextColumn("Priority", width="small"),
            "lead_status": st.column_config.TextColumn("Status", width="small"),
            "matched_services": st.column_config.TextColumn("Matched Services", width="large"),
            "response_time_ms": st.column_config.NumberColumn("Speed (ms)", width="small", format="%.0f ms"),
            "page_size_kb": st.column_config.NumberColumn("Size (KB)", width="small", format="%.1f KB"),
        },
    )
