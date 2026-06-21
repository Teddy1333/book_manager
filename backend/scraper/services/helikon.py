"""Helikon.bg book scraper implementation."""

import html as html_lib
import json
import re
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from services.base import BookResult, BookScraper

BASE_URL = "https://www.helikon.bg"
MOBILE_BASE_URL = "https://m.helikon.bg"


def _to_mobile_url(url: str) -> str:
    if url.startswith(MOBILE_BASE_URL):
        return url
    if url.startswith(BASE_URL):
        return MOBILE_BASE_URL + url[len(BASE_URL):]
    return url


def _parse_json_ld(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    try:
        data = json.loads(raw_text, strict=False)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    try:
        decoder = json.JSONDecoder(strict=False)
        data, _ = decoder.raw_decode(raw_text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', raw_text)
    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(cleaned)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _format_isbn(value: str | None) -> str | None:
    if not value:
        return value
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch.upper() == "X")
    if len(digits) == 10 and digits.startswith("954"):
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9]}"
    if len(digits) == 13 and (digits.startswith("978") or digits.startswith("979")):
        if digits[3:6] == "954":
            return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}-{digits[12]}"
    return value


def _strip_html(value: str | None) -> str | None:
    if not value:
        return value
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html_lib.unescape(text).split()).strip()


def _null_if_empty(value: str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


class HelikonScraper(BookScraper):
    """Scraper for helikon.bg online bookstore."""

    @property
    def name(self) -> str:
        return "helikon"

    @property
    def display_name(self) -> str:
        return "Helikon.bg"

    def search(self, query: str, limit: int = 5) -> list[BookResult]:
        if not query:
            return []
        search_url = f"{BASE_URL}/search/?q={quote(query)}"
        urls = self._extract_book_urls(search_url)[:limit]
        return [self._extract_book_info(url) for url in urls]

    def _extract_book_urls(self, html_url: str) -> list[str]:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="bg-BG",
            )
            page = context.new_page()
            page.goto(html_url, wait_until="domcontentloaded")

            try:
                page.wait_for_function(
                    "document.title.includes('Книжарници Хеликон')", timeout=5000
                )
            except Exception:
                browser.close()
                return []

            locators = page.locator(".product-img-wrap a").all()
            urls = [
                BASE_URL + loc.get_attribute("href")
                for loc in locators
                if loc.get_attribute("href")
            ]
            browser.close()
            return urls

    def _extract_book_info(self, book_url: str) -> BookResult:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 390, "height": 844}, locale="bg-BG"
            )
            page = context.new_page()
            page.goto(_to_mobile_url(book_url), wait_until="domcontentloaded")

            try:
                page.wait_for_selector("table", timeout=5000)
            except Exception:
                pass

            # Parse JSON-LD structured data
            json_ld = {}
            json_ld_el = page.locator("script[type='application/ld+json']")
            if json_ld_el.count() > 0:
                json_ld = _parse_json_ld(json_ld_el.first.inner_text())

            title = json_ld.get("name")

            author = None
            author_data = json_ld.get("author")
            if isinstance(author_data, dict):
                author = author_data.get("name")
            elif isinstance(author_data, list) and author_data:
                author = author_data[0].get("name")

            description = json_ld.get("description")
            if isinstance(description, str):
                description = _strip_html(description)

            cover_url = json_ld.get("image")

            # Fallback: extract title and author from page title
            if not title:
                page_title = page.title()
                if "\u300b" in page_title:  # 》
                    title_part = page_title.split("\u300b")[0]
                    title = title_part.replace("\u300a", "").strip() or None  # 《
                if not author and "|" in page_title:
                    parts = page_title.split("|")
                    if len(parts) >= 2:
                        candidate = parts[1].strip()
                        if candidate and "Книги" not in candidate and "Хеликон" not in candidate:
                            author = candidate

            # Parse table metadata
            isbn = publisher = pages = categories = None
            year = language = None
            rows = page.locator("table tr").all()
            for row in rows:
                cells = row.locator("td").all()
                if len(cells) >= 2:
                    key = cells[0].inner_text().strip()
                    value_cell = cells[1]
                    value_text = value_cell.inner_text().strip()
                    if "Категории" in key:
                        links = [a.inner_text().strip() for a in value_cell.locator("a").all()]
                        categories = ", ".join([v for v in links if v]) if links else " ".join(value_text.split())
                    elif "ISBN" in key:
                        isbn = " ".join(value_text.split())
                    elif "Издател" in key:
                        publisher = " ".join(value_text.split())
                    elif "Брой страници" in key:
                        pages = " ".join(value_text.split())
                    elif "Година на издаване" in key:
                        year = " ".join(value_text.split())
                    elif "Език" in key:
                        language = " ".join(value_text.split())

            # Fallback to JSON-LD for missing fields
            if not isbn and isinstance(json_ld.get("isbn"), str):
                isbn = json_ld.get("isbn").strip()
            if not publisher and isinstance(json_ld.get("publisher"), dict):
                publisher = json_ld.get("publisher", {}).get("name")
            if not pages and isinstance(json_ld.get("numberOfPages"), str):
                pages = json_ld.get("numberOfPages").strip()

            isbn = _format_isbn(isbn)
            browser.close()

            # Normalize pages
            if isinstance(pages, str) and pages.strip() in {"0", "0 стр.", "0 стр"}:
                pages = None

            if isinstance(description, str) and "<" in description:
                description = _strip_html(description)

            return BookResult(
                title=_null_if_empty(title),
                author=_null_if_empty(author),
                isbn=_null_if_empty(isbn),
                publisher=_null_if_empty(publisher),
                pages=_null_if_empty(pages),
                description=_null_if_empty(description),
                cover_url=_null_if_empty(cover_url),
                categories=_null_if_empty(categories),
                year=_null_if_empty(year),
                language=_null_if_empty(language),
                url=book_url,
                source=self.name,
            )
