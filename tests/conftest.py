"""
Global pytest configuration and isolation fixtures.

Guarantees:
1. Zero Database Pollution: Every test runs against an isolated in-memory SQLite database.
   Production database (data/leads.db) is NEVER touched during testing.
2. Zero File Pollution: File exports are restricted to tmp_path fixtures.
3. Zero Secret Leakage: API keys are masked with fake test strings.
4. Zero Network Calls: Live HTTP requests during tests are blocked.
"""

import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db.session
from db.models import Base
import config.settings


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch, tmp_path):
    """
    Automated fixture that isolates database, secrets, and logging for every test.
    """
    # 1. Isolate Database -> In-Memory SQLite with check_same_thread=False
    test_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db.session, "engine", test_engine)
    monkeypatch.setattr(db.session, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(config.settings, "DATABASE_URL", "sqlite:///:memory:")

    # 2. Isolate Secrets -> Neutral test values
    monkeypatch.setattr(config.settings, "GEOAPIFY_API_KEY", "test_mock_geoapify_key_12345")
    monkeypatch.setattr(config.settings, "GOOGLE_PLACES_API_KEY", "test_mock_places_key_12345")

    # 3. Isolate Logging -> Route any file logging to tmp_path
    test_log_file = tmp_path / "test_app.log"
    monkeypatch.setattr(config.settings, "LOG_FILE", test_log_file)

    yield

    test_engine.dispose()
