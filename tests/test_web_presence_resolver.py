"""
Tests for resolver/web_presence_resolver.py

Verifies:
- Facebook/Instagram tag detection from normalized _raw_tags (Fix #1)
- Contactable flag logic (Fix #5: monotonic)
- _raw_tags stripped from output
"""

import pytest
from resolver.web_presence_resolver import resolve_web_presence


class TestSocialTagDetection:
    """Verify social links are extracted from _raw_tags regardless of provider."""

    def test_facebook_tag_detected(self):
        """Lead with contact:facebook in _raw_tags -> facebook field populated."""
        leads = [{
            "business_name": "Test Clinic",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {"contact:facebook": "https://facebook.com/testclinic"},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["facebook"] == "https://facebook.com/testclinic"

    def test_instagram_tag_detected(self):
        """Lead with contact:instagram in _raw_tags -> instagram field populated."""
        leads = [{
            "business_name": "Fashion Store",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {"contact:instagram": "https://instagram.com/fashionstore"},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["instagram"] == "https://instagram.com/fashionstore"

    def test_linkedin_tag_detected(self):
        """Lead with contact:linkedin -> linkedin field populated."""
        leads = [{
            "business_name": "Corp Ltd",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {"contact:linkedin": "https://linkedin.com/company/corp"},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["linkedin"] == "https://linkedin.com/company/corp"

    def test_existing_social_not_overwritten(self):
        """If facebook is already set, _raw_tags should NOT overwrite it."""
        leads = [{
            "business_name": "Existing FB",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": "https://facebook.com/original",
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {"contact:facebook": "https://facebook.com/fromtags"},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["facebook"] == "https://facebook.com/original"

    def test_multiple_social_tags(self):
        """Both FB and IG found in raw tags."""
        leads = [{
            "business_name": "Social Biz",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {
                "contact:facebook": "https://fb.com/socialbiz",
                "contact:instagram": "https://ig.com/socialbiz",
            },
        }]
        result = resolve_web_presence(leads)
        assert result[0]["facebook"] == "https://fb.com/socialbiz"
        assert result[0]["instagram"] == "https://ig.com/socialbiz"


class TestContactableFlag:
    """Verify the contactable boolean is set correctly."""

    def test_contactable_with_phone(self):
        """Lead with phone -> contactable=True."""
        leads = [{
            "business_name": "Has Phone",
            "website": None,
            "phone": "+923001234567",
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["contactable"] is True

    def test_contactable_with_email(self):
        """Lead with email -> contactable=True."""
        leads = [{
            "business_name": "Has Email",
            "website": None,
            "phone": None,
            "email": "info@test.pk",
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["contactable"] is True

    def test_not_contactable_no_phone_no_email(self):
        """Lead with no phone and no email -> contactable=False."""
        leads = [{
            "business_name": "No Contact",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["contactable"] is False

    def test_website_alone_not_contactable(self):
        """Having only a website does NOT make a lead contactable
        (contactable = phone OR email specifically)."""
        leads = [{
            "business_name": "Website Only",
            "website": "https://test.pk",
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {},
        }]
        result = resolve_web_presence(leads)
        assert result[0]["contactable"] is False


class TestRawTagsCleanup:
    """Verify internal fields are stripped from output."""

    def test_raw_tags_stripped(self):
        """_raw_tags should not be present in the output dict."""
        leads = [{
            "business_name": "Cleanup Test",
            "website": None,
            "phone": None,
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
            "_raw_tags": {"contact:facebook": "https://fb.com/test"},
            "_source": "osm",
        }]
        result = resolve_web_presence(leads)
        assert "_raw_tags" not in result[0]
        assert "_source" not in result[0]

    def test_no_raw_tags_key_ok(self):
        """Leads without _raw_tags should not crash."""
        leads = [{
            "business_name": "No Tags",
            "website": None,
            "phone": "+923001234567",
            "email": None,
            "facebook": None,
            "instagram": None,
            "linkedin": None,
        }]
        result = resolve_web_presence(leads)
        assert result[0]["contactable"] is True
        assert "_raw_tags" not in result[0]
