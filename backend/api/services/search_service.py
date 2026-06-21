from os import getenv
from urllib.parse import quote

import httpx
import requests
from bs4 import BeautifulSoup
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import db_models
from services.book_service import serialize_book
from utils import log_lookup_warning, normalize_isbn

AI_SERVICE_URL = getenv("AI_SERVICE_URL", "http://localhost:8001")
SCRAPER_SERVICE_URL = getenv("SCRAPER_SERVICE_URL", "http://localhost:8002")


def ai_ocr(image: bytes, is_handwritten: bool = False) -> str:
    try:
        response = httpx.post(
            f"{AI_SERVICE_URL}/ocr",
            content=image,
            headers={"Content-Type": "application/octet-stream"},
            params={"is_handwritten": str(is_handwritten).lower()},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["text"]
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI service unavailable: {exc}") from exc


def ai_transcribe(audio: bytes, suffix: str = ".wav", language: str = "bg-BG") -> str:
    try:
        response = httpx.post(
            f"{AI_SERVICE_URL}/transcribe",
            content=audio,
            headers={"Content-Type": "application/octet-stream"},
            params={"suffix": suffix, "language": language},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["text"]
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI service unavailable: {exc}") from exc


def helikon_search(query: str, limit: int = 5) -> list[dict]:
    try:
        response = httpx.get(
            f"{SCRAPER_SERVICE_URL}/search",
            params={"q": query, "limit": limit},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Scraper service unavailable: {exc}") from exc


def google_books_search(query: str, limit: int = 5) -> list[dict]:
    try:
        response = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": limit},
            timeout=5,
        )
        if response.status_code in [429, 503]:
            log_lookup_warning(f"Google Books unavailable ({response.status_code}); trying fallback providers.")
            return []
        response.raise_for_status()
        results = []
        for item in response.json().get("items", []):
            info = item.get("volumeInfo", {})
            identifiers = info.get("industryIdentifiers", [])
            isbn = next(
                (entry.get("identifier") for entry in identifiers if entry.get("type") in {"ISBN_13", "ISBN_10"}),
                None,
            )
            results.append({
                "title": info.get("title"),
                "author": ", ".join(info.get("authors", [])) or None,
                "isbn": normalize_isbn(isbn) or None,
                "publisher": info.get("publisher"),
                "pages": str(info.get("pageCount")) if info.get("pageCount") else None,
                "description": info.get("description"),
                "cover_url": info.get("imageLinks", {}).get("thumbnail"),
                "source": "google_books",
                "tags": info.get("categories", []),
            })
        return results
    except Exception as exc:
        log_lookup_warning(f"Google Books lookup failed: {exc}")
        return []


def _open_library_work_edition_details(work_key: str | None) -> dict:
    if not work_key:
        return {}
    try:
        response = requests.get(
            f"http://openlibrary.org{work_key}/editions.json",
            params={"limit": 50},
            headers={"User-Agent": "book-manager/1.0"},
            timeout=7,
        )
        response.raise_for_status()
        entries = response.json().get("entries", [])
    except Exception as exc:
        log_lookup_warning(f"Open Library work editions lookup failed for {work_key}: {exc}")
        return {}

    preferred = [e for e in entries if e.get("number_of_pages")] or entries
    for edition in preferred:
        pages = edition.get("number_of_pages")
        isbn = next(
            (normalize_isbn(v) for v in [*edition.get("isbn_13", []), *edition.get("isbn_10", [])] if normalize_isbn(v)),
            None,
        )
        if pages or isbn:
            description = edition.get("description")
            if isinstance(description, dict):
                description = description.get("value")
            return {
                "title": edition.get("title"),
                "author": None,
                "isbn": isbn,
                "publisher": next((v for v in edition.get("publishers", []) if v), None),
                "pages": str(pages) if pages else None,
                "description": description if isinstance(description, str) else None,
            }
    return {}


def _open_library_edition_details(item: dict) -> dict:
    edition_keys = []
    if item.get("cover_edition_key"):
        edition_keys.append(item["cover_edition_key"])
    edition_keys.extend(item.get("edition_key", [])[:2])

    for key in dict.fromkeys(edition_keys):
        try:
            response = requests.get(
                f"http://openlibrary.org/books/{key}.json",
                headers={"User-Agent": "book-manager/1.0"},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            log_lookup_warning(f"Open Library edition lookup failed for {key}: {exc}")
            continue

        description = data.get("description")
        if isinstance(description, dict):
            description = description.get("value")

        isbn = next(
            (normalize_isbn(v) for v in [*data.get("isbn_13", []), *data.get("isbn_10", [])] if normalize_isbn(v)),
            None,
        )
        details = {
            "title": data.get("title"),
            "author": None,
            "isbn": isbn,
            "publisher": next((v for v in data.get("publishers", []) if v), None),
            "pages": str(data.get("number_of_pages")) if data.get("number_of_pages") else None,
            "description": description if isinstance(description, str) else None,
        }
        if not details["pages"] or not details["isbn"]:
            work = _open_library_work_edition_details(item.get("key"))
            details = {k: v or work.get(k) for k, v in details.items()}
        return details

    return _open_library_work_edition_details(item.get("key"))


def open_library_search(query: str, limit: int = 5) -> list[dict]:
    params: dict = {"limit": limit}
    normalized_isbn = normalize_isbn(query.removeprefix("isbn:"))
    if normalized_isbn and len(normalized_isbn) in {10, 13}:
        params["isbn"] = normalized_isbn
    else:
        params["title"] = query

    try:
        response = requests.get(
            "http://openlibrary.org/search.json",
            params=params,
            headers={"User-Agent": "book-manager/1.0"},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:
        log_lookup_warning(f"Open Library lookup failed: {exc}")
        return []

    results = []
    for item in response.json().get("docs", [])[:limit]:
        edition = _open_library_edition_details(item)
        isbn = edition.get("isbn") or next(
            (normalize_isbn(v) for v in item.get("isbn", []) if normalize_isbn(v)), None
        )
        cover_id = item.get("cover_i")
        results.append({
            "title": edition.get("title") or item.get("title"),
            "author": edition.get("author") or ", ".join(item.get("author_name", [])) or None,
            "isbn": isbn,
            "publisher": edition.get("publisher") or next((v for v in item.get("publisher", []) if v), None),
            "pages": edition.get("pages") or (str(item.get("number_of_pages_median")) if item.get("number_of_pages_median") else None),
            "description": edition.get("description"),
            "cover_url": f"http://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "source": "open_library",
            "tags": item.get("subject", [])[:5],
        })
    return [b for b in results if b["title"]]


def isbnsearch_lookup(isbn: str) -> list[dict]:
    response = requests.get(
        f"https://isbnsearch.org/isbn/{quote(isbn)}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    info = soup.select_one(".bookinfo")
    title = soup.select_one(".bookinfo h1")
    image = soup.select_one(".image img")
    if not info or not title:
        return []

    details: dict = {}
    for paragraph in info.select("p"):
        label, separator, value = paragraph.get_text(" ", strip=True).partition(":")
        if separator:
            details[label.strip().lower()] = value.strip()

    book_isbn = normalize_isbn(details.get("isbn-13") or details.get("isbn-10") or isbn)
    return [{
        "title": title.get_text(" ", strip=True),
        "author": details.get("author"),
        "isbn": book_isbn or isbn,
        "publisher": details.get("publisher"),
        "pages": None,
        "description": None,
        "cover_url": image.get("src") if image else None,
        "source": "isbnsearch",
        "tags": [],
    }]


def lookup_google_matches(q: str, limit: int = 5) -> list[dict]:
    matches = google_books_search(q, limit=limit)
    if not matches:
        matches = open_library_search(q, limit=limit)
    if not matches:
        try:
            matches = helikon_search(q, limit=limit)
        except Exception as exc:
            log_lookup_warning(f"Helikon lookup failed: {exc}")
            matches = []
    return matches


def search_books(db: Session, query: str, limit: int = 5) -> dict:
    clean_query = normalize_isbn(query)
    is_isbn = bool(clean_query and len(clean_query) in {10, 13})

    if is_isbn:
        local_books = db.query(db_models.Book).filter(db_models.Book.isbn == clean_query).all()
    else:
        like = f"%{query}%"
        local_books = (
            db.query(db_models.Book)
            .filter(or_(db_models.Book.title.ilike(like), db_models.Book.author.ilike(like)))
            .limit(limit)
            .all()
        )

    if local_books:
        return {"source": "local", "matches": [serialize_book(b) for b in local_books]}

    errors: list[str] = []

    if is_isbn:
        try:
            matches = isbnsearch_lookup(clean_query)
            if matches:
                return {"source": "isbnsearch", "matches": matches}
        except Exception as exc:
            errors.append(f"ISBNSearch failed: {exc}")

    try:
        term = f"isbn:{clean_query}" if is_isbn else query
        google = google_books_search(term, limit=limit)
        if google:
            return {"source": "google_books", "matches": google}
    except Exception as exc:
        errors.append(f"Google Books failed: {exc}")

    try:
        ol = open_library_search(clean_query if is_isbn else query, limit=limit)
        if ol:
            return {"source": "open_library", "matches": ol}
    except Exception as exc:
        errors.append(f"Open Library failed: {exc}")

    try:
        helikon = helikon_search(query, limit=limit)
        if helikon:
            return {"source": "helikon", "matches": helikon}
    except Exception as exc:
        errors.append(f"Helikon failed: {exc}")

    return {"source": "none", "matches": [], "errors": errors}
