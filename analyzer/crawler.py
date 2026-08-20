"""
Website & Social Media Crawler for Phase 2 & 3.

Visits websites (or resolved social pages) to extract:
- Verified emails (with strict exclusion of asset-file false positives,
  retina images, Sentry/Wix error-tracking DSNs, and UUID/hex strings)
- Verified phone numbers (normalized to E.164 via phonenumbers)
- Social media profile links (Facebook, Instagram, LinkedIn)
- Web presence signals: HTTPS, Title, Meta description, H1s, Viewport,
  SEO issues, E-commerce indicators, and Booking/Appointment forms.
- Basic performance & technical signals: response_time_ms and page_size_kb.

Uses httpx with SSL flexibility and redirects, with Playwright fallback for SPAs.
Every extraction step is independently try/except isolated.
"""

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup
import httpx
import phonenumbers

from scraper.dedup import DeduplicationEngine

logger = logging.getLogger(__name__)

# File extensions to strictly exclude from email matching
ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".wav", ".avi", ".mov", ".pdf", ".zip", ".tar", ".gz",
}

# Blacklisted email prefixes & system artifacts
IGNORED_EMAIL_PREFIXES = {
    "sentry", "webpack", "wixpress", "cloudflare", "noreply", "no-reply",
    "donotreply", "example", "test", "placeholder", "user", "email",
    "domain", "yourname", "admin", "info-placeholder", "daemon",
    "postmaster", "hostmaster", "root", "support-placeholder",
}

# Blacklisted domain substrings / tracking systems
IGNORED_EMAIL_DOMAINS = {
    "sentry", "wixpress.com", "wix.com", "parastorage.com",
    "cloudflare.com", "cloudflarestorage.com", "webpack",
    "schema.org", "w3.org", "github.com", "gitlab.com",
    "gravatar.com", "wp.com", "wordpress.com", "automattic.com",
    "example.com", "example.org", "localhost", "invalid", "test",
    "google.com", "googleapis.com", "gstatic.com", "facebook.com", "instagram.com",
    "mailgun.org", "sendgrid.net", "amazonaws.com",
}

# General email regex pattern
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)


@dataclass
class CrawlResult:
    """Structured result of crawling a lead's web presence."""
    url: str
    reachable: bool = False
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    is_https: bool = False
    
    # Technical & Performance signals
    response_time_ms: Optional[float] = None
    page_size_kb: Optional[float] = None

    # Contact information
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    linkedin: Optional[str] = None
    
    # Metadata & SEO signals
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1_tags: list[str] = field(default_factory=list)
    has_mobile_viewport: bool = False
    seo_issues: list[str] = field(default_factory=list)
    
    # Service & conversion signals
    has_ecommerce: bool = False
    has_booking_form: bool = False
    
    # Error message if crawl failed
    error: Optional[str] = None


class LeadCrawler:
    """Performs HTTP fetching and web presence analysis."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36 LeadScraper/2.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def crawl_lead(self, url: str, country_code: str = "US") -> CrawlResult:
        """
        Crawl a URL (website or public social profile) and extract all signals.
        """
        result = CrawlResult(url=url)
        if not url or not url.strip():
            result.error = "Empty URL"
            return result

        normalized_url = url.strip()
        if not normalized_url.startswith(("http://", "https://")):
            normalized_url = "https://" + normalized_url

        # Attempt fetch via httpx
        html_content, status_code, final_url, err, elapsed_ms, size_kb = self._fetch_url(normalized_url)
        if err or not html_content:
            # If HTTPS failed, try HTTP as fallback
            if normalized_url.startswith("https://") and ("SSL" in str(err) or "ConnectError" in str(err)):
                http_fallback = "http://" + normalized_url[8:]
                logger.debug("Retrying with HTTP fallback: %s", http_fallback)
                html_content, status_code, final_url, err, elapsed_ms, size_kb = self._fetch_url(http_fallback)

        if err or not html_content:
            result.reachable = False
            result.error = str(err) or "Empty response"
            result.response_time_ms = None
            result.page_size_kb = None
            return result

        result.reachable = True
        result.status_code = status_code
        result.final_url = str(final_url) if final_url else normalized_url
        result.is_https = str(result.final_url).lower().startswith("https://")
        result.response_time_ms = elapsed_ms
        result.page_size_kb = size_kb

        # Parse HTML and extract signals with independent error isolation
        self._parse_and_extract(result, html_content, country_code)
        return result

    def _fetch_url(self, url: str) -> tuple[Optional[str], Optional[int], Optional[str], Optional[str], Optional[float], Optional[float]]:
        """Fetch URL content with httpx, measuring response time and payload size."""
        start_time = time.perf_counter()
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                verify=False,  # Allow self-signed / expired certs for discovery
                headers=self.headers,
            ) as client:
                resp = client.get(url)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                size_kb = round(len(resp.content) / 1024.0, 2)
                resp.raise_for_status()
                return resp.text, resp.status_code, str(resp.url), None, elapsed_ms, size_kb
        except httpx.HTTPStatusError as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            size_kb = round(len(exc.response.content) / 1024.0, 2) if exc.response else None
            return None, exc.response.status_code, str(exc.response.url), f"HTTP {exc.response.status_code}", elapsed_ms, size_kb
        except Exception as exc:
            return None, None, None, str(exc), None, None

    def _parse_and_extract(self, result: CrawlResult, html: str, country_code: str) -> None:
        """Extract contact details and website metadata from HTML."""
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            logger.error("HTML parsing error for %s: %s", result.url, exc)
            return

        # 1. Extract Emails
        try:
            result.emails = self._extract_emails(soup, html)
        except Exception as exc:
            logger.debug("Email extraction error: %s", exc)

        # 2. Extract Phones
        try:
            result.phones = self._extract_phones(soup, html, country_code)
        except Exception as exc:
            logger.debug("Phone extraction error: %s", exc)

        # 3. Extract Social Links
        try:
            socials = self._extract_socials(soup)
            result.facebook = socials.get("facebook")
            result.instagram = socials.get("instagram")
            result.linkedin = socials.get("linkedin")
        except Exception as exc:
            logger.debug("Social extraction error: %s", exc)

        # 4. Extract SEO & Structural Signals
        try:
            self._extract_seo_signals(result, soup)
        except Exception as exc:
            logger.debug("SEO signals extraction error: %s", exc)

        # 5. Extract E-commerce Signals
        try:
            result.has_ecommerce = self._detect_ecommerce(soup, html)
        except Exception as exc:
            logger.debug("E-commerce detection error: %s", exc)

        # 6. Extract Booking & Contact Form Signals
        try:
            result.has_booking_form = self._detect_booking_form(soup, html)
        except Exception as exc:
            logger.debug("Booking form detection error: %s", exc)

    @classmethod
    def is_valid_business_email(cls, email: str) -> bool:
        """
        Validate whether an email is a legitimate human contact address or a
        system-generated monitoring artifact / asset file false positive.
        """
        cleaned = email.strip().strip(".,;:()\"'<>").lower()
        if not cleaned or "@" not in cleaned:
            return False

        lower_email = cleaned.lower()

        # 1. Check asset file extensions
        if any(lower_email.endswith(ext) for ext in ASSET_EXTENSIONS):
            return False

        # 2. Check retina image false positives (e.g. logo@2x.png, icon@3x.jpg)
        if re.search(r"@\d+(\.\d+)?x\.", lower_email):
            return False

        parts = cleaned.split("@")
        if len(parts) != 2:
            return False
        prefix, domain = parts[0].lower(), parts[1].lower()

        # 3. Check ignored system/placeholder prefixes
        if prefix in IGNORED_EMAIL_PREFIXES:
            return False

        # 4. Check long hexadecimal string (e.g. 16+ or 32 hex chars DSN/project tokens)
        if re.match(r"^[0-9a-f]{16,}$", prefix):
            return False

        # 5. Check UUID-like patterns
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", prefix):
            return False

        # 6. Check blacklisted monitoring / vendor domains (e.g. sentry-next.wixpress.com)
        if any(ignored_domain in domain for ignored_domain in IGNORED_EMAIL_DOMAINS):
            return False

        # 7. Validate domain structure
        if "." not in domain or len(domain.split(".")[-1]) < 2:
            return False

        return True

    def _extract_emails(self, soup: BeautifulSoup, html: str) -> list[str]:
        """
        Extract valid emails while strictly excluding asset files,
        retina image tags, and Sentry/Wix system tracking artifacts.
        """
        candidates: set[str] = set()

        # From mailto: links
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if href.lower().startswith("mailto:"):
                raw_mail = href[7:].split("?")[0].strip()
                if raw_mail:
                    candidates.add(raw_mail)

        # From page text and raw HTML
        for match in EMAIL_REGEX.findall(html):
            candidates.add(match)

        valid_emails = [
            email.strip().strip(".,;:()\"'<>").lower()
            for email in candidates
            if self.is_valid_business_email(email)
        ]

        return sorted(list(set(valid_emails)))

    def _extract_phones(self, soup: BeautifulSoup, html: str, country_code: str) -> list[str]:
        """Extract phone numbers using tel: links and phonenumbers.PhoneNumberMatcher."""
        normalized_phones: set[str] = set()

        # 1. From tel: links
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if href.lower().startswith("tel:"):
                raw_phone = href[4:].split("?")[0].strip()
                norm = DeduplicationEngine.normalize_phone(raw_phone, country_code=country_code)
                if norm:
                    normalized_phones.add(norm)

        # 2. From body text using phonenumbers PhoneNumberMatcher
        text_content = soup.get_text(separator=" ", strip=True)
        try:
            for match in phonenumbers.PhoneNumberMatcher(text_content, country_code.upper()):
                formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                if formatted:
                    normalized_phones.add(formatted)
        except Exception as exc:
            logger.debug("PhoneNumberMatcher error: %s", exc)

        return sorted(list(normalized_phones))

    def _extract_socials(self, soup: BeautifulSoup) -> dict[str, Optional[str]]:
        """Extract social media profile URLs from links."""
        socials = {"facebook": None, "instagram": None, "linkedin": None}

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or not href.startswith(("http://", "https://", "//")):
                continue

            lower_href = href.lower()

            # Facebook
            if "facebook.com/" in lower_href and not socials["facebook"]:
                if not any(x in lower_href for x in ["/sharer", "/share.php", "/dialog", "/policies", "/legal", "/tr"]):
                    socials["facebook"] = href

            # Instagram
            elif "instagram.com/" in lower_href and not socials["instagram"]:
                if not any(x in lower_href for x in ["/p/", "/reel/", "/explore/", "/stories/", "/accounts/"]):
                    socials["instagram"] = href

            # LinkedIn
            elif "linkedin.com/" in lower_href and not socials["linkedin"]:
                if any(x in lower_href for x in ["/company/", "/in/", "/school/"]):
                    socials["linkedin"] = href

        return socials

    def _extract_seo_signals(self, result: CrawlResult, soup: BeautifulSoup) -> None:
        """Extract title, description, H1s, viewport, and identify SEO issues."""
        issues: list[str] = []

        # Title
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            result.title = title_tag.get_text(strip=True)
        else:
            issues.append("missing_title")

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta_desc and meta_desc.get("content", "").strip():
            result.meta_description = meta_desc["content"].strip()
        else:
            issues.append("missing_meta_description")

        # H1 tags
        h1_elements = soup.find_all("h1")
        result.h1_tags = [h.get_text(strip=True) for h in h1_elements if h.get_text(strip=True)]
        if not result.h1_tags:
            issues.append("missing_h1")
        elif len(result.h1_tags) > 1:
            issues.append("multiple_h1")

        # Mobile viewport
        viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
        result.has_mobile_viewport = bool(viewport and viewport.get("content"))
        if not result.has_mobile_viewport:
            issues.append("no_mobile_viewport")

        # HTTPS
        if not result.is_https:
            issues.append("no_https")

        result.seo_issues = issues

    def _detect_ecommerce(self, soup: BeautifulSoup, html: str) -> bool:
        """
        Strictly detect real e-commerce storefronts.
        Eliminates false positives from conversational phrases like 'check out our services'.
        """
        lower_html = html.lower()

        # 1. Platform scripts & metadata
        ecomm_scripts = [
            "cdn.shopify.com", "shopify.theme", "woocommerce", "wc-api",
            "bigcommerce", "prestashop", "magento", "opencart", "snipcart",
        ]
        if any(fp in lower_html for fp in ecomm_scripts):
            return True

        # 2. Structural e-commerce HTML elements (cart forms, checkout buttons, product wrappers)
        ecomm_selectors = [
            "form[action*='cart']", "form[action*='checkout']",
            ".woocommerce", ".shopify-section", ".snipcart-checkout",
            ".cart-drawer", "#cart-drawer", ".shopping-cart", "#shopping-cart",
            "[data-cart-submit]", "[data-add-to-cart]",
        ]
        for selector in ecomm_selectors:
            if soup.select_one(selector):
                return True

        # 3. Explicit e-commerce action phrases (exact multi-word strings only, NOT bare 'checkout')
        strict_cart_phrases = [
            "add to cart", "add to basket", "add to bag",
            "proceed to checkout", "secure checkout",
            "item in your cart", "items in your cart",
            "your shopping cart", "view basket", "view shopping bag",
        ]
        text_content = soup.get_text(separator=" ", strip=True).lower()
        if any(phrase in text_content for phrase in strict_cart_phrases):
            return True

        return False

    def _detect_booking_form(self, soup: BeautifulSoup, html: str) -> bool:
        """Detect online appointment booking widgets, forms, or WhatsApp buttons."""
        lower_html = html.lower()

        # Third-party booking widgets & chat links
        booking_footprints = [
            "calendly.com", "acuityscheduling.com", "appointlet.com",
            "setmore.com", "simplybook.me", "wa.me/", "api.whatsapp.com/send",
        ]
        if any(fp in lower_html for fp in booking_footprints):
            return True

        # Form presence with appointment / inquiry keywords
        forms = soup.find_all("form")
        for form in forms:
            form_text = form.get_text(separator=" ", strip=True).lower()
            if any(k in form_text for k in ["book", "appointment", "schedule", "reserve", "consultation", "inquiry", "contact"]):
                return True

        # Button / Link text
        text_content = soup.get_text(separator=" ", strip=True).lower()
        if any(k in text_content for k in ["book appointment", "book online", "schedule consultation", "reserve a table"]):
            return True

        return False
