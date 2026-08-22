# Lead Scraper & Agency Qualification Engine

A high-performance B2B lead generation, website auditing, and sales qualification engine. Discovers business leads from OpenStreetMap (Overpass API) and Geoapify Places API, crawls their websites to extract verified contact details and technical performance metrics, matches them against 9 canonical digital agency services, calculates a 0–100 Opportunity Score, and exports outreach-ready spreadsheets to **Excel (`.xlsx`)** and **CSV**.

Powered by **MySQL** for persistent production storage, with two independent interfaces and a full CLI:
1. **React Web Product (`frontend/`)**: Modern, client-facing web application with live KPI stats, interactive lead discovery, dynamic filter sidebar, sortable table with flat priority badges, lead detail modal, and collision-resistant file exports.
2. **Streamlit Operator App (`app.py`)**: Internal operator dashboard for fast ad-hoc scraping, manual qualification, and team workflows.
3. **FastAPI REST API (`api/main.py`)**: High-speed typed REST API backend powering the React frontend and external integrations.
4. **Python Automation Engine & CLI (`main.py`)**: Core extraction, deduplication, crawling, scoring, and export pipeline.

---

## 🏗️ Architecture & Component Overview

```
Lead Scraper Automation/
├── analyzer/
│   └── crawler.py               # Web crawler, email/phone extractor, SEO & performance analyzer
├── api/
│   └── main.py                  # FastAPI REST API backend (REST endpoints, background tasks, Swagger /docs)
├── config/
│   └── settings.py              # Configuration, MySQL connection pooling, category mappings, logging
├── data/
│   ├── leads.db                 # Historical SQLite database (for migration to MySQL)
│   └── sample_export.csv        # Realistic deliverable sample export
├── db/
│   ├── crud.py                  # Database CRUD helper queries
│   ├── models.py                # SQLAlchemy models (Lead and ScrapeLog)
│   └── session.py               # Database engine & MySQL connection pool management
├── export/
│   └── exporter.py              # Multi-filter CSV and XLSX export engine
├── frontend/                    # React Web Application (Client-Facing Product)
│   ├── src/
│   │   ├── api/client.js        # Centralized API client with VITE_API_BASE_URL
│   │   ├── components/          # StatsBar, SearchForm, FilterSidebar, LeadsTable, LeadDetailModal, ExportButtons
│   │   ├── App.jsx              # Main dashboard coordinator
│   │   └── index.css            # Clean flat design system (no gradients, flat badges, sentence case)
│   ├── .env.example             # Frontend environment template
│   └── package.json             # Vite React dependencies
├── matcher/
│   └── service_matcher.py       # 9 canonical agency service qualification rules
├── pipeline/
│   ├── analyzer_orchestrator.py # Batch crawler and scoring orchestrator
│   ├── coverage_reporter.py     # Real-time fill rate & data quality metrics
│   ├── discovery_merger.py      # Cross-provider deduplication & metadata merger
│   └── orchestrator.py          # Multi-source discovery orchestrator (OSM + Geoapify)
├── resolver/
│   └── web_presence_resolver.py # Social tag standardizer & contactable manager
├── scoring/
│   └── lead_scorer.py           # 0-100 opportunity scoring & reason generator
├── scraper/
│   ├── base_provider.py         # Abstract DiscoveryProvider base class
│   ├── dedup.py                 # E.164 phone, domain, and RapidFuzz deduplication engine
│   ├── geoapify_provider.py     # Geoapify Places discovery client
│   └── osm_provider.py          # OSM Overpass client with Nominatim geocoding
├── scripts/
│   └── migrate_sqlite_to_mysql.py # SQLite -> MySQL one-time data migration utility
├── tests/                       # Automated test suite (78 tests in in-memory SQLite sandbox)
├── .env.example                 # Root environment template (MySQL credentials & Geoapify API key)
├── requirements.txt             # Python dependencies (FastAPI, Uvicorn, Streamlit, PyMySQL, Cryptography)
├── app.py                       # Streamlit web dashboard (Internal operator tool)
└── main.py                      # CLI entrypoint (run, scrape, analyze, export, info)
```

---

## 🚀 Quick Start Guide

### 1. Environment & MySQL Setup

#### Step 1: Install Python Dependencies
```bash
pip install -r requirements.txt
```

#### Step 2: Create the MySQL Database
Log into your local or remote MySQL instance (port 3306):
```sql
CREATE DATABASE lead_scraper CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### Step 3: Configure Root `.env`
Copy `.env.example` to `.env` and set your credentials:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=lead_scraper

GEOAPIFY_API_KEY=your_geoapify_key_here
```

#### Step 4: (Optional) Migrate Historical Leads to MySQL
If migrating from an existing SQLite database:
```bash
python scripts/migrate_sqlite_to_mysql.py
```

---

### 2. Running the Applications

#### A. The React Web Product (Client-Facing UI)
1. **Start the FastAPI Backend** (Terminal 1):
   ```bash
   uvicorn api.main:app --reload
   ```
   *FastAPI server runs on `http://localhost:8000` with Swagger docs at `http://localhost:8000/docs`.*

2. **Start the React Frontend** (Terminal 2):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   *Opens the React web application on `http://localhost:5173`.*

#### B. The Streamlit App (Internal Operator Tool)
```bash
streamlit run app.py
```
*Opens the Streamlit dashboard on `http://localhost:8501`.*

#### C. Command Line Automation (CLI)
```bash
# Full discovery + crawl + scoring + Excel export
python main.py run --country US --city Miami --category "real estate" --count 20 --export-out data/miami_real_estate.xlsx --export-format xlsx --contactable

# Database health stats
python main.py info
```

---

## 🔌 FastAPI REST Endpoints

| Method | Endpoint | Description | Request / Query Params |
|---|---|---|---|
| `POST` | `/leads/search` | Trigger background lead scrape + web crawl + qualification. | JSON Body: `{ "country": "US", "city": "Miami", "category": "dentist", "count": 20 }` (Returns `202 Accepted` with `job_id`, or `409 Conflict` if another job is running). |
| `GET` | `/leads/jobs/{job_id}` | Poll execution status and progress of a background search job. | Path param: `job_id` (Returns `pending`, `running`, `complete`, or `failed`). |
| `GET` | `/leads` | List and live-filter leads with pagination. | Query params: `priority`, `service`, `city`, `category`, `min_score`, `has_email`, `has_phone`, `no_website`, `contactable`, `page`, `page_size`. |
| `GET` | `/leads/{id}` | Get full single lead profile including performance signals and provenance. | Path param: `id` (Returns full lead details or `404 Not Found`). |
| `GET` | `/leads/export` | Download live-filtered leads spreadsheet with descriptive filename. | Query params: `format` (`csv` or `xlsx`), plus all filtering parameters. Streams file directly. |
| `GET` | `/stats` | Real-time database metrics, priority breakdown, and dropdown lists. | Returns total leads, HOT/WARM/COLD counts, contactable counts, fill rates, and distinct canonical categories/cities. |

---

## 🏢 Supported Categories & Target Markets

Supported across **United States (`US`)**, **Canada (`CA`)**, **United Kingdom (`GB`)**, **Germany (`DE`)**, **United Arab Emirates (`AE`)**, and globally:

- **Real Estate & Property**: `"real estate"`, `"realtor"`, `"property"`
- **Healthcare & Dental**: `"dentist"`, `"dental clinic"`, `"orthodontist"`, `"doctor"`, `"medical clinic"`, `"pharmacy"`
- **Legal & Financial**: `"lawyer"`, `"attorney"`, `"law firm"`, `"accountant"`
- **Personal Care & Wellness**: `"salon"`, `"barber"`, `"spa"`
- **Fitness & Sports**: `"gym"`, `"fitness center"`
- **Automotive & Local Services**: `"car repair"`, `"auto repair"`, `"mechanic"`, `"car wash"`
- **Fashion & Retail**: `"clothing store"`, `"boutique"`, `"shoe store"`, `"jewelry"`, `"furniture"`
- **Food & Dining**: `"restaurant"`, `"cafe"`, `"bakery"`, `"bar"`, `"hotel"`

---

## 🎯 9 Canonical Agency Services

Each lead is audited and matched against 9 digital service opportunities:
1. `Web Development` (no website or non-functional site)
2. `Web App Development` (custom portals and e-commerce carts)
3. `Mobile App Development` (high-traffic booking & retail businesses)
4. `SEO` (missing metadata, weak heading structure, low search presence)
5. `Social Media Marketing` (lacking Facebook, Instagram, or LinkedIn)
6. `Social Media Management` (active social optimization)
7. `Google Ads` (high commercial intent niches lacking paid ads)
8. `Google Shopping` (e-commerce storefronts selling physical goods)
9. `AI Automation` (appointment-based businesses lacking automated booking widgets or chatbots)

---

## 🧪 Automated Testing & Sandbox Isolation

The project includes an automated test suite with **100% database & network isolation** (runs against an in-memory SQLite sandbox):

```bash
pytest tests/ -v
```
*(All 78 unit & integration tests pass in ~4 seconds with zero external network calls and zero production database touches).*
