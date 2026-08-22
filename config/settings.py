"""
Configuration and environment settings for Lead Scraper Automation.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# -- Secrets ----------------------------------------------------------------
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
GEOAPIFY_API_KEY: str = os.getenv("GEOAPIFY_API_KEY", "")

# -- MySQL Database Configuration -------------------------------------------
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
DB_USER: str = os.getenv("DB_USER", "root")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
DB_NAME: str = os.getenv("DB_NAME", "lead_scraper")

# Explicit DATABASE_URL override if provided in .env
_ENV_DATABASE_URL = os.getenv("DATABASE_URL")
if _ENV_DATABASE_URL:
    DATABASE_URL: str = _ENV_DATABASE_URL
else:
    # Construct MySQL connection URL with URL-encoded password and utf8mb4 charset
    if DB_PASSWORD:
        encoded_pwd = quote_plus(DB_PASSWORD)
        DATABASE_URL = f"mysql+pymysql://{DB_USER}:{encoded_pwd}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    else:
        DATABASE_URL = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

# Fallback path for SQLite data export/migration
SQLITE_DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'leads.db'}"

# -- Google Places API (New, v1) --------------------------------------------
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_PAGE_SIZE = 20
PLACES_PAGE_DELAY_SEC = 2.0
PLACES_MAX_PAGES = 3

PLACES_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.internationalPhoneNumber",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.types",
    "places.googleMapsUri",
    "nextPageToken",
])

# -- OSM Overpass & Nominatim API -------------------------------------------
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "LeadScraperBot/1.0 (contact@leadscraper.local)"
NOMINATIM_REQUEST_DELAY = 1.0  # Nominatim usage policy: max 1 req/sec

# Robust, multi-server list of Overpass API mirrors
OSM_OVERPASS_MIRRORS: list[str] = [
    "https://overpass.freemap.sk/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OSM_QUERY_TIMEOUT = 25
OSM_REQUEST_TIMEOUT = 30
OSM_REQUEST_DELAY = 1.5  # delay between consecutive Overpass requests

# -- Geoapify API -----------------------------------------------------------
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_REQUEST_TIMEOUT = 30

# Canonical category mapping table to merge near-duplicates
CANONICAL_CATEGORY_MAP: dict[str, str] = {
    # Clothing & Fashion
    "clothes": "clothing store",
    "clothing": "clothing store",
    "apparel": "clothing store",
    "boutique": "clothing store",
    "fashion": "clothing store",
    "garments": "clothing store",
    "shoe store": "clothing store",
    "shoes": "clothing store",

    # Real Estate & Property
    "estate agent": "real estate",
    "realtor": "real estate",
    "property": "real estate",
    "real estate agency": "real estate",
    "real_estate": "real estate",

    # Healthcare & Dental
    "dental clinic": "dentist",
    "dental": "dentist",
    "dental care": "dentist",
    "orthodontist": "dentist",
    "physician": "doctor",
    "medical clinic": "clinic",

    # Automotive
    "auto repair": "car repair",
    "mechanic": "car repair",

    # Fitness & Wellness
    "fitness": "gym",
    "fitness center": "gym",

    # Food & Hospitality
    "coffee shop": "cafe",
    "coffee": "cafe",
    "eatery": "restaurant",
    "diner": "restaurant",

    # Legal & Financial
    "law firm": "lawyer",
    "attorney": "lawyer",
    "accounting": "accountant",
}


def normalize_category(category: str | None) -> str:
    """Normalize raw or variant category string to canonical form."""
    if not category:
        return ""
    cat_clean = category.strip().lower()
    return CANONICAL_CATEGORY_MAP.get(cat_clean, cat_clean)


GEOAPIFY_CATEGORY_MAP: dict[str, str] = {
    # Real Estate & Property
    "real estate": "service.estate_agent",
    "estate agent": "service.estate_agent",
    "realtor": "service.estate_agent",
    "property": "service.estate_agent",
    "real estate agency": "service.estate_agent",

    # Clothing, Fashion & Retail
    "clothing store": "commercial.clothing",
    "clothing": "commercial.clothing",
    "clothes": "commercial.clothing",
    "apparel": "commercial.clothing",
    "boutique": "commercial.clothing",
    "fashion": "commercial.clothing",
    "garments": "commercial.clothing",
    "tailor": "commercial.clothing",
    "shoe store": "commercial.clothing",
    "shoes": "commercial.clothing",
    "jewelry": "commercial.jewelry",
    "electronics": "commercial.elektronics",
    "furniture": "commercial.furniture_and_interior",
    "bookstore": "commercial.books",
    "books": "commercial.books",
    "gift shop": "commercial.gift_and_souvenir",
    "shopping mall": "commercial.shopping_mall",
    "mall": "commercial.shopping_mall",

    # Healthcare & Medical
    "dentist": "healthcare.dentist",
    "dental clinic": "healthcare.dentist",
    "dental": "healthcare.dentist",
    "dental care": "healthcare.dentist",
    "orthodontist": "healthcare.dentist",
    "doctor": "healthcare.doctor_gp",
    "physician": "healthcare.doctor_gp",
    "medical clinic": "healthcare.clinic_or_praxis",
    "hospital": "healthcare.hospital",
    "clinic": "healthcare.clinic_or_praxis",
    "pharmacy": "healthcare.pharmacy",
    "chemist": "healthcare.pharmacy",
    "drugstore": "healthcare.pharmacy",
    "optician": "healthcare.optician",
    "veterinary": "healthcare.veterinary",

    # Food & Hospitality
    "restaurant": "catering.restaurant",
    "eatery": "catering.restaurant",
    "diner": "catering.restaurant",
    "pizzeria": "catering.restaurant",
    "cafe": "catering.cafe",
    "coffee shop": "catering.cafe",
    "coffee": "catering.cafe",
    "bakery": "catering.bakery",
    "fast food": "catering.fast_food",
    "burger": "catering.fast_food",
    "pizza": "catering.fast_food",
    "bar": "catering.bar",
    "pub": "catering.pub",
    "hotel": "accommodation.hotel",
    "motel": "accommodation.motel",
    "hostel": "accommodation.hostel",

    # Groceries & Food Retail
    "supermarket": "commercial.supermarket",
    "grocery": "commercial.supermarket",
    "grocery store": "commercial.supermarket",
    "convenience store": "commercial.convenience",
    "mart": "commercial.supermarket",

    # Services & Personal Care
    "salon": "service.beauty.hairdresser",
    "hair salon": "service.beauty.hairdresser",
    "barber": "service.beauty.hairdresser",
    "hairdresser": "service.beauty.hairdresser",
    "beauty": "service.beauty",
    "beauty salon": "service.beauty",
    "spa": "service.beauty.spa",
    "gym": "sport.fitness",
    "fitness": "sport.fitness",
    "fitness center": "sport.fitness",
    "car repair": "service.vehicle.car_repair",
    "auto repair": "service.vehicle.car_repair",
    "mechanic": "service.vehicle.car_repair",
    "car wash": "service.vehicle.car_wash",
    "laundry": "service.laundry",
    "dry cleaning": "service.dry_cleaning",

    # Professional & Education
    "lawyer": "office.lawyer",
    "attorney": "office.lawyer",
    "law firm": "office.lawyer",
    "accountant": "office.accountant",
    "accounting": "office.accountant",
    "school": "education.school",
    "university": "education.university",
    "college": "education.college",
}

# -- Deduplication ----------------------------------------------------------
FUZZY_MATCH_THRESHOLD = 90

# -- Coverage reporting -----------------------------------------------------
COVERAGE_WARNING_THRESHOLD = 0.15  # 15%

# -- Scoring weights --------------------------------------------------------
SCORING_WEIGHTS: dict = {
    "no_website": 30, "low_rating": 15, "few_reviews": 10,
    "no_social": 10, "no_https": 10, "poor_seo": 15, "no_mobile": 10,
}
SERVICE_RULES: dict = {}

# -- Consolidated Logging ---------------------------------------------------
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3


def setup_logging(level: int = logging.INFO) -> None:
    """Configure consolidated root logger with rotating file handler (5MB, 3 backups)."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if root_logger.handlers:
        return
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
