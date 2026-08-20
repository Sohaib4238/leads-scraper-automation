"""
Unit tests for analyzer/crawler.py

Verifies:
- Email extraction and strict exclusion of asset files, retina images,
  Sentry/Wix DSN strings, and long hex/UUID patterns
- Phone number extraction and E.164 normalization
- Social link extraction
- SEO signals and structural defect detection
- Strict e-commerce detection
- Booking form detection
- Performance & technical signals (response_time_ms, page_size_kb)
"""

import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from analyzer.crawler import LeadCrawler, CrawlResult


class TestEmailExtraction:
    """Test email discovery and strict filtering of assets and monitoring DSNs."""

    def test_extract_valid_emails(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <a href="mailto:info@business.com">Contact Us</a>
                <p>Reach us at support@business.com or sales@business.com</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        emails = crawler._extract_emails(soup, html)
        assert emails == ["info@business.com", "sales@business.com", "support@business.com"]

    def test_exclude_asset_files(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <a href="mailto:real@company.com">Real Email</a>
                <p>image@2x.png</p>
                <p>icon@3x.jpg</p>
                <p>style@main.css</p>
                <p>bundle@app.js</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        emails = crawler._extract_emails(soup, html)
        assert emails == ["real@company.com"]

    def test_exclude_system_and_placeholder_prefixes(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <p>noreply@company.com</p>
                <p>test@example.com</p>
                <p>placeholder@domain.com</p>
                <p>contact@company.com</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        emails = crawler._extract_emails(soup, html)
        assert emails == ["contact@company.com"]

    def test_exclude_sentry_wix_and_hex_uuid_dsns(self):
        """Verify Sentry DSNs and Wix tracking strings are strictly rejected."""
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <p>605a7baede844d278b89dc95ae0a9123@sentry-next.wixpress.com</p>
                <p>2062d0a4929b45348643784b5cb39c36@sentry.wixpress.com</p>
                <p>abcdef1234567890abcdef1234567890@ingest.sentry.io</p>
                <p>human.contact@marea-restaurant.de</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        emails = crawler._extract_emails(soup, html)
        assert emails == ["human.contact@marea-restaurant.de"]
        assert not any("sentry" in e for e in emails)
        assert not any("wixpress" in e for e in emails)


class TestPhoneExtraction:
    """Test phone discovery and E.164 normalization."""

    def test_extract_pakistani_phones(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <a href="tel:+923001234567">Call Now</a>
                <p>Direct: 0321-9876543</p>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        phones = crawler._extract_phones(soup, html, country_code="PK")
        assert "+923001234567" in phones
        assert "+923219876543" in phones

    def test_extract_international_phones(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <a href="tel:+493012345678">Berlin Clinic</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        phones = crawler._extract_phones(soup, html, country_code="DE")
        assert "+493012345678" in phones


class TestSocialExtraction:
    """Test social profile URL extraction."""

    def test_extract_social_links(self):
        crawler = LeadCrawler()
        html = """
        <html>
            <body>
                <a href="https://www.facebook.com/dentalcarepk">Facebook</a>
                <a href="https://www.instagram.com/dentalcare_official/">Instagram</a>
                <a href="https://www.linkedin.com/company/dentalcare/">LinkedIn</a>
                <a href="https://facebook.com/sharer/sharer.php?u=foo">Share on FB</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        socials = crawler._extract_socials(soup)
        assert socials["facebook"] == "https://www.facebook.com/dentalcarepk"
        assert socials["instagram"] == "https://www.instagram.com/dentalcare_official/"
        assert socials["linkedin"] == "https://www.linkedin.com/company/dentalcare/"


class TestSignalsAndSEO:
    """Test SEO defects, e-commerce, and booking form signals."""

    def test_seo_issues_detected(self):
        crawler = LeadCrawler()
        html = "<html><head><title>Test</title></head><body><h1>One</h1><h1>Two</h1></body></html>"
        result = CrawlResult(url="http://test.com")
        soup = BeautifulSoup(html, "html.parser")
        crawler._extract_seo_signals(result, soup)
        assert "missing_meta_description" in result.seo_issues
        assert "multiple_h1" in result.seo_issues
        assert "no_mobile_viewport" in result.seo_issues
        assert "no_https" in result.seo_issues

    def test_ecommerce_detection(self):
        crawler = LeadCrawler()
        html_ecomm = "<html><body><button class='add-to-cart'>Add to Basket</button></body></html>"
        soup_ecomm = BeautifulSoup(html_ecomm, "html.parser")
        assert crawler._detect_ecommerce(soup_ecomm, html_ecomm) is True

        html_none = "<html><body><p>Check out our dental plans and services</p></body></html>"
        soup_none = BeautifulSoup(html_none, "html.parser")
        assert crawler._detect_ecommerce(soup_none, html_none) is False

    def test_booking_form_detection(self):
        crawler = LeadCrawler()
        html_book = "<html><body><a href='https://calendly.com/dr-ahmed/30min'>Book</a></body></html>"
        soup_book = BeautifulSoup(html_book, "html.parser")
        assert crawler._detect_booking_form(soup_book, html_book) is True


class TestPerformanceSignals:
    """Verify response_time_ms and page_size_kb capture and null safety."""

    def test_performance_signals_captured_on_successful_crawl(self):
        crawler = LeadCrawler()
        mock_resp = MagicMock()
        mock_resp.text = "<html><head><title>Mocked Site</title></head><body>Hello World</body></html>"
        mock_resp.content = b"<html><head><title>Mocked Site</title></head><body>Hello World</body></html>"
        mock_resp.status_code = 200
        mock_resp.url = "https://mocksite.de"

        with patch("httpx.Client.get", return_value=mock_resp):
            result = crawler.crawl_lead("https://mocksite.de")
            assert result.reachable is True
            assert result.response_time_ms is not None
            assert result.response_time_ms >= 0.0
            assert result.page_size_kb is not None
            assert result.page_size_kb > 0.0

    def test_performance_signals_null_on_failed_crawl(self):
        crawler = LeadCrawler()
        with patch("httpx.Client.get", side_effect=Exception("Connection refused")):
            result = crawler.crawl_lead("https://unreachable-domain-12345.com")
            assert result.reachable is False
            assert result.response_time_ms is None
            assert result.page_size_kb is None
            assert result.error is not None
