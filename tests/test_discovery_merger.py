"""
Tests for pipeline/discovery_merger.py

Verifies cross-provider dedup works on name+address alone (the common case
when phone/domain are both missing from discovery sources).
"""

import pytest
from pipeline.discovery_merger import merge_discovery_results


class TestCrossProviderDedup:
    """Leads from OSM + Geoapify with similar name+address should merge."""

    def test_same_business_different_providers_merges(self):
        """
        OSM: 'Dr Ahmed Dental, Clifton'
        Geoapify: 'Dr. Ahmed Dental Clinic, Clifton'
        -> Merged into one lead with discovery_sources: ['geoapify', 'osm']
        """
        osm_leads = [{
            "business_name": "Dr Ahmed Dental Clinic",
            "address": "Block 5, Clifton",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "osm",
        }]
        geo_leads = [{
            "business_name": "Dr. Ahmed Dental Clinic",
            "address": "Block 5 Clifton",
            "city": "Karachi",
            "website": "https://ahmed-dental.pk",
            "phone": "+923001234567",
            "email": None,
            "_raw_tags": {"contact:facebook": "https://fb.com/ahmed"},
            "_source": "geoapify",
        }]

        merged = merge_discovery_results({"osm": osm_leads, "geoapify": geo_leads})
        assert len(merged) == 1
        lead = merged[0]
        assert set(lead["discovery_sources"]) == {"osm", "geoapify"}

    def test_field_fill_from_best_source(self):
        """
        OSM has phone but no website.
        Geoapify has website but no phone.
        -> Merged lead has BOTH.
        """
        osm_leads = [{
            "business_name": "Karachi Auto Parts",
            "address": "5 Factory Lane",
            "city": "Karachi",
            "website": None,
            "phone": "+923001111111",
            "email": None,
            "_raw_tags": {},
            "_source": "osm",
        }]
        geo_leads = [{
            "business_name": "Karachi Auto Parts",
            "address": "5 Factory Lane",
            "city": "Karachi",
            "website": "https://karachiauto.pk",
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "geoapify",
        }]

        merged = merge_discovery_results({"osm": osm_leads, "geoapify": geo_leads})
        assert len(merged) == 1
        lead = merged[0]
        assert lead["phone"] == "+923001111111"
        assert lead["website"] == "https://karachiauto.pk"

    def test_different_businesses_not_merged(self):
        """Different businesses at different addresses should stay separate."""
        osm_leads = [{
            "business_name": "Alpha Dental Surgery",
            "address": "10 Ocean Blvd",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "osm",
        }]
        geo_leads = [{
            "business_name": "Zenith Eye Hospital",
            "address": "777 Mountain Rd",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "geoapify",
        }]

        merged = merge_discovery_results({"osm": osm_leads, "geoapify": geo_leads})
        assert len(merged) == 2

    def test_single_source_works(self):
        """Only OSM results -> works fine with discovery_sources: ['osm']."""
        osm_leads = [{
            "business_name": "Test Business",
            "address": "123 Main St",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "osm",
        }]

        merged = merge_discovery_results({"osm": osm_leads})
        assert len(merged) == 1
        assert merged[0]["discovery_sources"] == ["osm"]

    def test_raw_tags_merged(self):
        """Raw tags from both providers should be combined."""
        osm_leads = [{
            "business_name": "Test Shop",
            "address": "1 Test St",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {"contact:facebook": "https://fb.com/test"},
            "_source": "osm",
        }]
        geo_leads = [{
            "business_name": "Test Shop",
            "address": "1 Test St",
            "city": "Karachi",
            "website": None,
            "phone": None,
            "email": None,
            "_raw_tags": {"contact:instagram": "https://instagram.com/test"},
            "_source": "geoapify",
        }]

        merged = merge_discovery_results({"osm": osm_leads, "geoapify": geo_leads})
        assert len(merged) == 1
        assert merged[0]["_raw_tags"]["contact:facebook"] == "https://fb.com/test"
        assert merged[0]["_raw_tags"]["contact:instagram"] == "https://instagram.com/test"

    def test_domain_match_across_providers(self):
        """Same website from different providers -> merge."""
        osm_leads = [{
            "business_name": "My Clinic",
            "address": "",
            "city": "Lahore",
            "website": "https://myclinic.pk",
            "phone": None,
            "email": None,
            "_raw_tags": {},
            "_source": "osm",
        }]
        geo_leads = [{
            "business_name": "My Clinic Lahore",
            "address": "Different Address Text",
            "city": "Lahore",
            "website": "https://myclinic.pk",
            "phone": "+924212345678",
            "email": None,
            "_raw_tags": {},
            "_source": "geoapify",
        }]

        merged = merge_discovery_results({"osm": osm_leads, "geoapify": geo_leads})
        assert len(merged) == 1
        assert merged[0]["phone"] == "+924212345678"
