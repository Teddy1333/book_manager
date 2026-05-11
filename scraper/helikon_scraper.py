from playwright.sync_api import sync_playwright
from urllib.parse import quote
import json
import html as html_lib
import re
import sys

BASE_URL = "https://www.helikon.bg"
MOBILE_BASE_URL = "https://m.helikon.bg"


def _to_mobile_url(url):
    if url.startswith(MOBILE_BASE_URL):
        return url
    if url.startswith(BASE_URL):
        return MOBILE_BASE_URL + url[len(BASE_URL):]
    return url


def _parse_json_ld(raw_text):
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(raw_text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _format_isbn(value):
    if not value:
        return value
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch.upper() == "X")
    if len(digits) == 10 and digits.startswith("954"):
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9]}"
    if len(digits) == 13 and (digits.startswith("978") or digits.startswith("979")):
        if digits[3:6] == "954":
            return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}-{digits[12]}"
    return value


def _strip_html(value):
    if not value:
        return value
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html_lib.unescape(text).split()).strip()


def extract_book_urls(html_url):
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="bg-BG"
        )
        page = context.new_page()
        page.goto(html_url, wait_until="domcontentloaded")

        try:
            page.wait_for_function("document.title.includes('Книжарници Хеликон')", timeout=5000)
        except:
            browser.close()
            return []

        locators = page.locator(".product-img-wrap a").all()
        urls = [BASE_URL + loc.get_attribute("href") for loc in locators if loc.get_attribute("href")]
        browser.close()
        return urls


def extract_book_info(book_url):
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale="bg-BG")
        page = context.new_page()
        page.goto(_to_mobile_url(book_url), wait_until="domcontentloaded")

        try:
            page.wait_for_selector("table", timeout=5000)
        except:
            pass

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

        isbn = publisher = pages = categories = None
        year = cover = language = weight = dimensions = barcode = None
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
                elif "Баркод" in key:
                    barcode = " ".join(value_text.split())
                elif "Издател" in key:
                    publisher = " ".join(value_text.split())
                elif "Брой страници" in key:
                    pages = " ".join(value_text.split())
                elif "Година на издаване" in key:
                    year = " ".join(value_text.split())
                elif "Корици" in key:
                    cover = " ".join(value_text.split())
                elif "Език" in key:
                    language = " ".join(value_text.split())
                elif "Тегло" in key:
                    weight = " ".join(value_text.split())
                elif "Размери" in key:
                    dimensions = " ".join(value_text.split())

        if not isbn and isinstance(json_ld.get("isbn"), str):
            isbn = json_ld.get("isbn").strip()
        if not publisher and isinstance(json_ld.get("publisher"), dict):
            publisher = json_ld.get("publisher", {}).get("name")
        if not pages and isinstance(json_ld.get("numberOfPages"), str):
            pages = json_ld.get("numberOfPages").strip()

        isbn = _format_isbn(isbn)
        barcode = _format_isbn(barcode)

        browser.close()

        def _unknown_if_empty(value):
            if value is None:
                return "неизвестно"
            if isinstance(value, str) and not value.strip():
                return "неизвестно"
            return value

        pages_value = pages
        if isinstance(pages_value, str) and pages_value.strip() in {"0", "0 стр.", "0 стр"}:
            pages_value = None

        if isinstance(description, str) and "<" in description:
            description = _strip_html(description)

        return {
            "title": _unknown_if_empty(title),
            "author": _unknown_if_empty(author),
            "isbn": _unknown_if_empty(isbn),
            "barcode": _unknown_if_empty(barcode),
            "publisher": _unknown_if_empty(publisher),
            "pages": _unknown_if_empty(pages_value),
            "year": _unknown_if_empty(year),
            "cover": _unknown_if_empty(cover),
            "language": _unknown_if_empty(language),
            "weight": _unknown_if_empty(weight),
            "dimensions": _unknown_if_empty(dimensions),
            "categories": _unknown_if_empty(categories),
            "description": _unknown_if_empty(description),
            "url": book_url,
            "source": "helikon"
        }


def search_books(query, limit=5):
    search_url = f"{BASE_URL}/search/?q={quote(query)}"
    urls = extract_book_urls(search_url)[:limit]
    books = [extract_book_info(url) for url in urls]
    return books


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    books = search_books("игото", limit=1)
    for b in books:
        print("\n--- BOOK ---")
        for k, v in b.items():
            print(f"{k}: {v}")
