"""
Unit tests for export/exporter.py

Verifies:
- Multi-filter AND logic (priority, service, category/industry, city, min_score, contactable, etc.)
- Output format generation for CSV and XLSX
- Comma-separated list serialization for matched_services and discovery_sources
- Technical & performance signal column exports (response_time_ms, page_size_kb)
- Empty results and edge cases
"""

import json
from pathlib import Path
import pytest
import pandas as pd

from export.exporter import LeadExporter
from db.models import Lead
from db.session import get_session


@pytest.fixture(autouse=True)
def seed_test_leads():
    """Seed test leads and strictly clean them up after each test to prevent DB pollution."""
    test_ids = []
    with get_session() as session:
        lead1 = Lead(
            business_name="__TEST__ Berlin Dental Spa",
            category="dentist",
            city="Berlin",
            country="DE",
            phone="+4930123456",
            email="info@berlindental.de",
            website="https://berlindental.de",
            score=45,
            priority="WARM",
            contactable=True,
            response_time_ms=185.5,
            page_size_kb=42.3,
            matched_services=json.dumps(["SEO", "Google Ads", "Web App Development"]),
            discovery_sources=json.dumps(["osm", "geoapify"]),
            reason="Priority WARM (Score 45/100): Test reasons.",
        )
        lead2 = Lead(
            business_name="__TEST__ Karachi Local Barber",
            category="salon",
            city="Karachi",
            country="PK",
            phone=None,
            email=None,
            website=None,
            score=70,
            priority="HOT",
            contactable=False,
            response_time_ms=None,
            page_size_kb=None,
            matched_services=json.dumps(["Web Development", "SEO", "Social Media Marketing"]),
            discovery_sources=json.dumps(["osm"]),
            reason="Priority HOT (Score 70/100): No website found.",
        )
        lead3 = Lead(
            business_name="__TEST__ London Dental Studio",
            category="dentist",
            city="London",
            country="GB",
            phone="+442079460999",
            email=None,
            website="https://londondental.co.uk",
            score=15,
            priority="COLD",
            contactable=True,
            response_time_ms=95.2,
            page_size_kb=18.6,
            matched_services=json.dumps(["Social Media Management"]),
            discovery_sources=json.dumps(["geoapify"]),
            reason="Priority COLD (Score 15/100): Minimal issues.",
        )
        lead4 = Lead(
            business_name="__TEST__ Dubai Premier Properties",
            category="real estate",
            city="Dubai",
            country="AE",
            phone="+97141234567",
            email="sales@dubaipremier.ae",
            website="https://dubaipremier.ae",
            score=50,
            priority="WARM",
            contactable=True,
            response_time_ms=310.8,
            page_size_kb=88.4,
            matched_services=json.dumps(["Google Ads", "SEO"]),
            discovery_sources=json.dumps(["geoapify"]),
            reason="Priority WARM (Score 50/100): Real estate portal.",
        )
        session.add_all([lead1, lead2, lead3, lead4])
        session.commit()
        test_ids = [lead1.id, lead2.id, lead3.id, lead4.id]

    yield

    # Clean up test leads immediately after test
    with get_session() as session:
        session.query(Lead).filter(Lead.id.in_(test_ids)).delete(synchronize_session=False)
        session.commit()


class TestLeadExporter:
    """Test suite for LeadExporter functionality."""

    def test_export_csv_multi_filter_and_logic(self, tmp_path):
        out_csv = tmp_path / "test_export.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            city="Berlin",
            priority="WARM",
            contactable=True,
            service="SEO",
        )
        assert len(df) >= 1
        for _, row in df.iterrows():
            assert row["city"].lower() == "berlin"
            assert row["priority"] == "WARM"
            assert row["contactable"] is True
            assert "SEO" in row["matched_services"]
        assert out_csv.exists()

    def test_export_category_filter_alone(self, tmp_path):
        out_csv = tmp_path / "category_filter.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            category="real estate",
        )
        assert len(df) >= 1
        for _, row in df.iterrows():
            assert "real estate" in row["category"].lower()
            assert "dentist" not in row["category"].lower()

    def test_export_category_combined_with_priority(self, tmp_path):
        """Verify category/industry filter combined with priority (e.g. category='dentist', priority='WARM')."""
        out_csv = tmp_path / "dentist_warm.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            category="dentist",
            priority="WARM",
        )
        assert len(df) >= 1
        for _, row in df.iterrows():
            assert "dentist" in row["category"].lower()
            assert row["priority"] == "WARM"

    def test_export_industry_alias(self, tmp_path):
        """Verify industry parameter alias works identically to category."""
        out_csv = tmp_path / "industry_alias.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            industry="real estate",
        )
        assert len(df) >= 1
        for _, row in df.iterrows():
            assert "real estate" in row["category"].lower()

    def test_performance_signals_exported(self, tmp_path):
        """Verify response_time_ms and page_size_kb are included in exported columns."""
        out_csv = tmp_path / "performance_check.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            city="Berlin",
        )
        assert "response_time_ms" in df.columns
        assert "page_size_kb" in df.columns
        test_row = df[df["business_name"] == "__TEST__ Berlin Dental Spa"]
        if not test_row.empty:
            assert float(test_row.iloc[0]["response_time_ms"]) == 185.5
            assert float(test_row.iloc[0]["page_size_kb"]) == 42.3

    def test_export_xlsx_format(self, tmp_path):
        out_xlsx = tmp_path / "test_export.xlsx"
        df = LeadExporter.export_leads(
            output_path=str(out_xlsx),
            format="xlsx",
            country="DE",
        )
        assert out_xlsx.exists()
        loaded_df = pd.read_excel(out_xlsx)
        assert len(loaded_df) == len(df)

    def test_matched_services_comma_separated_formatting(self, tmp_path):
        out_csv = tmp_path / "formatting_check.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            city="Berlin",
        )
        test_row = df[df["business_name"] == "__TEST__ Berlin Dental Spa"]
        if not test_row.empty:
            row = test_row.iloc[0]
            assert row["matched_services"] == "SEO, Google Ads, Web App Development"
            assert "[" not in row["matched_services"]
            assert "'" not in row["matched_services"]
            assert row["discovery_sources"] == "osm, geoapify"

    def test_boolean_contact_filters(self, tmp_path):
        out_csv = tmp_path / "bool_filters.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            has_email=True,
            has_phone=True,
        )
        for _, row in df.iterrows():
            assert bool(row["email"])
            assert bool(row["phone"])

    def test_no_website_filter(self, tmp_path):
        out_csv = tmp_path / "no_web.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            no_website=True,
        )
        for _, row in df.iterrows():
            assert not row["website"]

    def test_discovery_source_filter(self, tmp_path):
        out_csv = tmp_path / "source_filter.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            discovery_source="geoapify",
        )
        for _, row in df.iterrows():
            assert "geoapify" in row["discovery_sources"].lower()

    def test_empty_results_handling(self, tmp_path):
        out_csv = tmp_path / "empty.csv"
        df = LeadExporter.export_leads(
            output_path=str(out_csv),
            format="csv",
            city="NonExistentCity12345",
        )
        assert len(df) == 0
        assert out_csv.exists()
