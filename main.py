import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta, time
from os import getenv
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import quote, urlparse

import requests
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from bs4 import BeautifulSoup

from ai.ocr import extract_text_from_image, ocr_status
from ai.speech import transcribe_audio
from ai.suggestions import suggest_books_for_user
from database import db_models
from database.db_manager import engine, get_db

SECRET_KEY = getenv("BOOK_MANAGER_SECRET_KEY", "diplomna_rabota_pu_key")
ALGORITHM = "HS256"
BASE_DIR = Path(__file__).resolve().parent

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(
    title="Book Diary API",
    description="Backend for book management, AI OCR, voice notes, recommendations, analytics, and sharing.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db_models.Base.metadata.create_all(bind=engine)
app.mount("/app", StaticFiles(directory=BASE_DIR / "static", html=True), name="book_journal_app")


@app.exception_handler(RuntimeError)
def runtime_error_handler(_request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


class BookIn(BaseModel):
    title: str = Field(min_length=1)
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pages: str | None = None
    description: str | None = None
    cover_url: str | None = None
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_isbn(value)
        if normalized and len(normalized) not in {10, 13}:
            raise ValueError("ISBN must contain 10 or 13 digits")
        return normalized or None


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pages: str | None = None
    description: str | None = None
    cover_url: str | None = None
    tags: list[str] | None = None

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_isbn(value)
        if normalized and len(normalized) not in {10, 13}:
            raise ValueError("ISBN must contain 10 or 13 digits")
        return normalized or None


class ProgressIn(BaseModel):
    current_page: int = Field(ge=0)
    total_pages: int | None = Field(default=None, ge=1)
    source: str = "manual"


class NoteIn(BaseModel):
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=0)
    note_type: str = "manual"


class NoteUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    page: int | None = Field(default=None, ge=0)
    note_type: str | None = None


class ShareImportIn(BaseModel):
    url: str | None = None
    token: str | None = None


class VoiceNoteIn(BaseModel):
    page: int | None = Field(default=None, ge=0)
    audio_format: str = "wav"


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)
) -> db_models.User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(db_models.User).filter(db_models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def serialize_book(book: db_models.Book) -> dict:
    latest_progress = (
        sorted(book.progress_entries, key=lambda item: item.created_at, reverse=True)[0]
        if book.progress_entries
        else None
    )
    total_pages = latest_progress.total_pages if latest_progress else _pages_as_int(book.pages)
    percentage = None
    if latest_progress and total_pages:
        percentage = round((latest_progress.current_page / total_pages) * 100, 2)

    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "publisher": book.publisher,
        "pages": book.pages,
        "description": book.description,
        "cover_url": book.cover_url,
        "source": book.source,
        "tags": [tag.name for tag in book.tags],
        "latest_progress": {
            "current_page": latest_progress.current_page,
            "total_pages": total_pages,
            "percentage": percentage,
            "source": latest_progress.source,
            "created_at": latest_progress.created_at.isoformat(),
        }
        if latest_progress
        else None,
    }


def serialize_note(note: db_models.Note) -> dict:
    return {
        "id": note.id,
        "book_id": note.book_id,
        "text": note.text,
        "page": note.page,
        "note_type": note.note_type,
        "image_path": note.image_path,
        "audio_path": note.audio_path,
        "created_at": note.created_at.isoformat(),
    }


def serialize_shared_book(book: db_models.Book) -> dict:
    data = serialize_book(book)
    data["notes"] = [
        serialize_note(note)
        for note in sorted(book.notes, key=lambda item: item.created_at, reverse=True)
    ]
    return data


def normalize_isbn(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X")


def _pages_as_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _log_lookup_warning(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))


def _get_book_for_user(db: Session, book_id: int, user_id: int) -> db_models.Book:
    book = (
        db.query(db_models.Book)
        .filter(db_models.Book.id == book_id, db_models.Book.owner_id == user_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def _get_note_for_user(db: Session, book_id: int, note_id: int, user_id: int) -> db_models.Note:
    note = (
        db.query(db_models.Note)
        .filter(
            db_models.Note.id == note_id,
            db_models.Note.book_id == book_id,
            db_models.Note.owner_id == user_id,
        )
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def _set_tags(db: Session, book: db_models.Book, tag_names: list[str]) -> None:
    cleaned = sorted({name.strip().lower() for name in tag_names if name.strip()})
    tags = []
    for name in cleaned:
        tag = db.query(db_models.Tag).filter(db_models.Tag.name == name).first()
        if not tag:
            tag = db_models.Tag(name=name)
            db.add(tag)
        tags.append(tag)
    book.tags = tags


def _ensure_unique_isbn(
    db: Session, user_id: int, isbn: str | None, current_book_id: int | None = None
) -> None:
    normalized = normalize_isbn(isbn)
    if not normalized:
        return
    query = db.query(db_models.Book).filter(
        db_models.Book.owner_id == user_id,
        db_models.Book.isbn == normalized,
    )
    if current_book_id is not None:
        query = query.filter(db_models.Book.id != current_book_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Book with this ISBN already exists")


def _share_token_from_value(value: str | None) -> str:
    if not value or not value.strip():
        raise HTTPException(status_code=422, detail="Share URL or token is required")

    cleaned = value.strip()
    parsed = urlparse(cleaned)
    path = parsed.path if parsed.scheme or parsed.netloc else cleaned
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) >= 2 and parts[-2] == "share":
        return parts[-1]
    if len(parts) == 1:
        return parts[0]
    raise HTTPException(status_code=422, detail="Share URL must look like /share/{token}")


def _import_shared_book(payload: ShareImportIn, db: Session, user: db_models.User) -> dict:
    token = _share_token_from_value(payload.token or payload.url)
    link = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")

    source = link.book
    _ensure_unique_isbn(db, user.id, source.isbn)
    book = db_models.Book(
        title=source.title,
        author=source.author,
        isbn=source.isbn,
        publisher=source.publisher,
        pages=source.pages,
        description=source.description,
        cover_url=source.cover_url,
        source="shared_import",
        owner_id=user.id,
    )
    _set_tags(db, book, [tag.name for tag in source.tags])
    db.add(book)
    db.flush()

    for source_note in sorted(source.notes, key=lambda item: item.created_at):
        db.add(
            db_models.Note(
                book_id=book.id,
                owner_id=user.id,
                text=source_note.text,
                page=source_note.page,
                note_type=f"shared_{source_note.note_type or 'note'}",
                image_path=source_note.image_path,
                audio_path=source_note.audio_path,
            )
        )

    db.commit()
    db.refresh(book)
    return serialize_shared_book(book)


def _google_books_search(query: str, limit: int = 5) -> list[dict]:
    try:
        response = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": limit},
            timeout=5,
        )
        if response.status_code in [429, 503]:
            _log_lookup_warning(f"Google Books unavailable ({response.status_code}); trying fallback providers.")
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

    except Exception as e:
        _log_lookup_warning(f"Google Books lookup failed: {e}")
        return []


def _open_library_search(query: str, limit: int = 5) -> list[dict]:
    params = {"limit": limit}
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
    except Exception as e:
        _log_lookup_warning(f"Open Library lookup failed: {e}")
        return []

    results = []
    for item in response.json().get("docs", [])[:limit]:
        edition = _open_library_edition_details(item)
        isbn = (
            edition.get("isbn")
            or next((normalize_isbn(value) for value in item.get("isbn", []) if normalize_isbn(value)), None)
        )
        cover_id = item.get("cover_i")
        results.append(
            {
                "title": edition.get("title") or item.get("title"),
                "author": edition.get("author") or ", ".join(item.get("author_name", [])) or None,
                "isbn": isbn,
                "publisher": edition.get("publisher") or next((value for value in item.get("publisher", []) if value), None),
                "pages": edition.get("pages")
                or (str(item.get("number_of_pages_median")) if item.get("number_of_pages_median") else None),
                "description": edition.get("description"),
                "cover_url": f"http://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
                "source": "open_library",
                "tags": item.get("subject", [])[:5],
            }
        )
    return [book for book in results if book["title"]]


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
        except Exception as e:
            _log_lookup_warning(f"Open Library edition lookup failed for {key}: {e}")
            continue

        description = data.get("description")
        if isinstance(description, dict):
            description = description.get("value")

        isbn = next(
            (
                normalize_isbn(value)
                for value in [*data.get("isbn_13", []), *data.get("isbn_10", [])]
                if normalize_isbn(value)
            ),
            None,
        )

        details = {
            "title": data.get("title"),
            "author": None,
            "isbn": isbn,
            "publisher": next((value for value in data.get("publishers", []) if value), None),
            "pages": str(data.get("number_of_pages")) if data.get("number_of_pages") else None,
            "description": description if isinstance(description, str) else None,
        }
        if not details["pages"] or not details["isbn"]:
            work_details = _open_library_work_edition_details(item.get("key"))
            details = {key: value or work_details.get(key) for key, value in details.items()}
        return details

    return _open_library_work_edition_details(item.get("key"))


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
    except Exception as e:
        _log_lookup_warning(f"Open Library work editions lookup failed for {work_key}: {e}")
        return {}

    preferred_entries = [edition for edition in entries if edition.get("number_of_pages")] or entries
    for edition in preferred_entries:
        pages = edition.get("number_of_pages")
        isbn = next(
            (
                normalize_isbn(value)
                for value in [*edition.get("isbn_13", []), *edition.get("isbn_10", [])]
                if normalize_isbn(value)
            ),
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
                "publisher": next((value for value in edition.get("publishers", []) if value), None),
                "pages": str(pages) if pages else None,
                "description": description if isinstance(description, str) else None,
            }

    return {}


def _lookup_google_matches(q: str, limit: int = 5) -> list[dict]:
    matches = _google_books_search(q, limit=limit)

    if not matches:
        matches = _open_library_search(q, limit=limit)

    if not matches:
        try:
            matches = _helikon_search(q, limit=limit)
        except Exception as exc:
            _log_lookup_warning(f"Helikon lookup failed: {exc}")
            matches = []

    return matches

#def _google_books_search(query: str, limit: int = 5) -> list[dict]:
#    response = requests.get(
#        "https://www.googleapis.com/books/v1/volumes",
#        params={"q": query, "maxResults": limit},
#        timeout=10,
#    )
#    response.raise_for_status()
#    results = []
#    for item in response.json().get("items", []):
#        info = item.get("volumeInfo", {})
#        identifiers = info.get("industryIdentifiers", [])
#        isbn = next(
#            (entry.get("identifier") for entry in identifiers if entry.get("type") in {"ISBN_13", "ISBN_10"}),
#            None,
#        )
#        results.append(
#            {
#                "title": info.get("title"),
#                "author": ", ".join(info.get("authors", [])) or None,
#                "isbn": normalize_isbn(isbn) or None,
#                "publisher": info.get("publisher"),
#                "pages": str(info.get("pageCount")) if info.get("pageCount") else None,
#                "description": info.get("description"),
#                "cover_url": info.get("imageLinks", {}).get("thumbnail"),
#                "source": "google_books",
#                "tags": info.get("categories", []),
#            }
#        )
#    return results


def _isbnsearch_lookup(isbn: str) -> list[dict]:
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

    details = {}
    for paragraph in info.select("p"):
        label, separator, value = paragraph.get_text(" ", strip=True).partition(":")
        if separator:
            details[label.strip().lower()] = value.strip()

    book_isbn = normalize_isbn(details.get("isbn-13") or details.get("isbn-10") or isbn)
    return [
        {
            "title": title.get_text(" ", strip=True),
            "author": details.get("author"),
            "isbn": book_isbn or isbn,
            "publisher": details.get("publisher"),
            "pages": None,
            "description": None,
            "cover_url": image.get("src") if image else None,
            "source": "isbnsearch",
            "tags": [],
        }
    ]


def _helikon_search(query: str, limit: int = 5) -> list[dict]:
    import importlib

    scraper = importlib.import_module("scraper.helikon_scraper")
    return scraper.search_books(query)


# Заменяме или допълваме съществуващата _search_isbn с тази универсална логика
def _search_books(db: Session, query: str, limit: int = 5) -> dict:
    """
    Универсална функция, която решава дали търсим по ISBN или по заглавие/автор.
    """
    # Проверка дали заявката е ISBN (числа, 10 или 13 символа)
    clean_query = normalize_isbn(query)
    is_isbn = clean_query and len(clean_query) in {10, 13}

    # 1. Търсене в локалната база
    if is_isbn:
        local_books = db.query(db_models.Book).filter(db_models.Book.isbn == clean_query).all()
    else:
        # Търсене по заглавие или автор, ако не е ISBN
        like = f"%{query}%"
        local_books = db.query(db_models.Book).filter(
            or_(db_models.Book.title.ilike(like), db_models.Book.author.ilike(like))
        ).limit(limit).all()

    if local_books:
        return {"source": "local", "matches": [serialize_book(book) for book in local_books]}

    # 2. Външно търсене (ако не е намерено локално)
    errors = []

    # Ако е ISBN, търсим първо с ISBN-специфичните методи
    if is_isbn:
        try:
            matches = _isbnsearch_lookup(clean_query)
            if matches: return {"source": "isbnsearch", "matches": matches}
        except Exception as e:
            errors.append(f"ISBNSearch failed: {e}")

    # Общо търсене в Google (работи и за ISBN, и за заглавия)
    try:
        search_term = f"isbn:{clean_query}" if is_isbn else query
        google_matches = _google_books_search(search_term, limit=limit)
        if google_matches:
            return {"source": "google_books", "matches": google_matches}
    except Exception as e:
        errors.append(f"Google Books failed: {e}")

    try:
        open_library_matches = _open_library_search(clean_query if is_isbn else query, limit=limit)
        if open_library_matches:
            return {"source": "open_library", "matches": open_library_matches}
    except Exception as e:
        errors.append(f"Open Library failed: {e}")

    # Fallback към Хеликон
    try:
        helikon_matches = _helikon_search(query, limit=limit)
        if helikon_matches:
            return {"source": "helikon", "matches": helikon_matches}
    except Exception as e:
        errors.append(f"Helikon failed: {e}")
    return {"source": "none", "matches": [], "errors": errors}


def _latest_progress_by_book(books: list[db_models.Book]) -> dict[int, db_models.ReadingProgress]:
    latest = {}
    for book in books:
        if book.progress_entries:
            latest[book.id] = sorted(
                book.progress_entries, key=lambda item: item.created_at, reverse=True
            )[0]
    return latest


def _daily_progress(books: list[db_models.Book], days: int = 7) -> list[dict]:
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days - 1)
    totals = {start_date + timedelta(days=index): 0 for index in range(days)}

    for book in books:
        entries = sorted(book.progress_entries, key=lambda item: item.created_at)
        previous_page = 0
        for entry in entries:
            entry_date = entry.created_at.date()
            pages_read = max(entry.current_page - previous_page, 0)
            if entry_date in totals:
                totals[entry_date] += pages_read
            previous_page = max(previous_page, entry.current_page)

    return [{"date": day.isoformat(), "pages": totals[day]} for day in sorted(totals)]


def build_user_stats(db: Session, user: db_models.User) -> dict:
    books = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id).all()
    latest_progress = _latest_progress_by_book(books)
    total_pages = sum(entry.current_page for entry in latest_progress.values())
    completed_books = 0
    for book in books:
        entry = latest_progress.get(book.id)
        total = entry.total_pages if entry else _pages_as_int(book.pages)
        if entry and total and entry.current_page >= total:
            completed_books += 1

    tag_pages = defaultdict(int)
    for book in books:
        pages = latest_progress.get(book.id).current_page if book.id in latest_progress else 0
        for tag in book.tags:
            tag_pages[tag.name] += pages

    top_genres = [
        {"tag": tag, "pages": pages}
        for tag, pages in sorted(tag_pages.items(), key=lambda item: item[1], reverse=True)[:3]
    ]

    return {
        "books_count": len(books),
        "notes_count": sum(len(book.notes) for book in books),
        "completed_books": completed_books,
        "total_read_pages": total_pages,
        "top_genres": top_genres,
        "last_7_days": _daily_progress(books),
    }


@app.get(
    "/",
    summary="API overview",
    description="Returns basic API metadata and documentation links.",
)
def api_overview():
    return {
        "name": "Book Diary API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    summary="Health check",
    description="Returns a lightweight status response for deployment checks.",
)
def health_check():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@app.get(
    "/ai/status",
    summary="AI feature status",
    description="Reports local OCR dependency availability for photo and handwriting features.",
)
def ai_status():
    return {"ocr": ocr_status()}


@app.post(
    "/signup",
    summary="Create user account",
    description="Registers a new user with a username and password.",
)
def signup(username: str, password: str, db: Session = Depends(get_db)):
    if db.query(db_models.User).filter(db_models.User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = db_models.User(username=username, hashed_password=get_password_hash(password))
    db.add(new_user)
    db.commit()
    return {"status": "User created"}


@app.post(
    "/token",
    summary="Login",
    description="Authenticates a user and returns a bearer access token.",
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(db_models.User).filter(db_models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong username or password")

    access_token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post(
    "/books",
    status_code=201,
    summary="Add book",
    description="Creates a book in the authenticated user's library.",
)
def create_book(
    payload: BookIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    _ensure_unique_isbn(db, user.id, payload.isbn)
    book = db_models.Book(
        title=payload.title,
        author=payload.author,
        isbn=payload.isbn,
        publisher=payload.publisher,
        pages=payload.pages,
        description=payload.description,
        cover_url=payload.cover_url,
        source=payload.source,
        owner_id=user.id,
    )
    _set_tags(db, book, payload.tags)
    db.add(book)
    db.commit()
    db.refresh(book)
    return serialize_book(book)


@app.get(
    "/books",
    summary="List books",
    description="Lists the authenticated user's books with optional text and tag filters.",
)
def list_books(
    q: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    query = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                db_models.Book.title.ilike(like),
                db_models.Book.author.ilike(like),
                db_models.Book.isbn.ilike(like),
            )
        )
    if tag:
        query = query.join(db_models.Book.tags).filter(db_models.Tag.name == tag.strip().lower())
    return [serialize_book(book) for book in query.order_by(db_models.Book.title).all()]


@app.post(
    "/books/import/share",
    status_code=201,
    summary="Import shared book",
    description="Imports a book and its notes from another user's public share link.",
)
def import_shared_book(
    payload: ShareImportIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return _import_shared_book(payload, db, user)


@app.get(
    "/books/{book_id}",
    summary="Get book",
    description="Returns one book from the authenticated user's library.",
)
def get_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return serialize_book(_get_book_for_user(db, book_id, user.id))


@app.patch(
    "/books/{book_id}",
    summary="Update book",
    description="Updates editable metadata and tags for one book.",
)
def update_book(
    book_id: int,
    payload: BookUpdate,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "isbn" in data:
        _ensure_unique_isbn(db, user.id, data["isbn"], current_book_id=book.id)
    tags = data.pop("tags", None)
    for key, value in data.items():
        setattr(book, key, value)
    if tags is not None:
        _set_tags(db, book, tags)
    db.commit()
    db.refresh(book)
    return serialize_book(book)


@app.delete(
    "/books/{book_id}",
    status_code=204,
    summary="Delete book",
    description="Deletes one book and its related progress, notes, and share links.",
)
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    db.delete(book)
    db.commit()


@app.get(
    "/lookup/google",
    summary="Search Google Books",
    description="Searches Google Books by title, author, keyword, or ISBN query.",
)
def lookup_google(q: str, limit: int = Query(default=5, ge=1, le=20)):
    return _lookup_google_matches(q, limit=limit)

@app.get(
    "/lookup/isbn/{isbn}",
    summary="Search by ISBN",
    description="Looks for an ISBN locally first, then Google Books, then Helikon.",
)
def lookup_isbn(isbn: str, db: Session = Depends(get_db)):
    return _search_books(db, isbn, limit=5)


@app.get(
    "/lookup/helikon",
    summary="Search Helikon",
    description="Searches the Helikon scraper as a fallback or direct bookstore lookup.",
)
def lookup_helikon(q: str, limit: int = Query(default=5, ge=1, le=10)):
    return _helikon_search(q, limit=limit)


@app.get(
    "/tags",
    summary="List tags",
    description="Lists all tags used by the authenticated user's books.",
)
def list_tags(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    books = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id).all()
    tag_counts = defaultdict(int)
    for book in books:
        for tag in book.tags:
            tag_counts[tag.name] += 1
    return [
        {"name": name, "books_count": count}
        for name, count in sorted(tag_counts.items(), key=lambda item: item[0])
    ]


@app.post(
    "/books/import/google",
    status_code=201,
    summary="Import Google book",
    description="Imports the best Google Books match into the authenticated user's library.",
)
def import_google_book(
    q: str,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    try:
        matches = _google_books_search(q, limit=1)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Google Books lookup failed: {exc}") from exc
    if not matches:
        raise HTTPException(status_code=404, detail="No book found")
    return create_book(BookIn(**matches[0]), db=db, user=user)


@app.post(
    "/books/import/isbn/{isbn}",
    status_code=201,
    summary="Import book by ISBN",
    description="Imports a book by ISBN using local check, Google Books, and Helikon fallback.",
)
def import_book_by_isbn(
    isbn: str,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    normalized = normalize_isbn(isbn)
    _ensure_unique_isbn(db, user.id, normalized)
    result = _search_books(db, normalized, limit=1)
    if not result["matches"]:
        raise HTTPException(status_code=404, detail="No book found")
    return create_book(BookIn(**result["matches"][0]), db=db, user=user)


@app.post(
    "/books/{book_id}/progress",
    status_code=201,
    summary="Add reading progress",
    description="Stores a manual reading progress entry for a book.",
)
def add_progress(
    book_id: int,
    payload: ProgressIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    total_pages = payload.total_pages or _pages_as_int(book.pages)
    if total_pages and payload.current_page > total_pages:
        raise HTTPException(status_code=422, detail="Current page cannot exceed total pages")
    entry = db_models.ReadingProgress(
        book_id=book.id,
        current_page=payload.current_page,
        total_pages=total_pages,
        source=payload.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    percentage = round((entry.current_page / entry.total_pages) * 100, 2) if entry.total_pages else None
    return {
        "id": entry.id,
        "book_id": book.id,
        "current_page": entry.current_page,
        "total_pages": entry.total_pages,
        "percentage": percentage,
        "source": entry.source,
        "created_at": entry.created_at.isoformat(),
    }


@app.post(
    "/books/{book_id}/progress/photo",
    status_code=201,
    summary="AI OCR progress from photo",
    description="Extracts a page number from a photo using Tesseract or EasyOCR for handwritten input.",
)
def add_progress_from_photo(
    book_id: int,
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    is_handwritten: bool = False,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    text = extract_text_from_image(image, is_handwritten=is_handwritten)
    numbers = [int(part) for part in "".join(ch if ch.isdigit() else " " for ch in text).split()]
    if not numbers:
        raise HTTPException(status_code=422, detail="Could not detect a page number from the image")
    return add_progress(
        book_id,
        ProgressIn(current_page=max(numbers), source="photo"),
        db=db,
        user=user,
    )


@app.post(
    "/books/{book_id}/notes",
    status_code=201,
    summary="Add note",
    description="Creates a manual note for a book.",
)
def create_note(
    book_id: int,
    payload: NoteIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    note = db_models.Note(
        book_id=book.id,
        owner_id=user.id,
        text=payload.text,
        page=payload.page,
        note_type=payload.note_type,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return serialize_note(note)


@app.get(
    "/books/{book_id}/notes",
    summary="List notes",
    description="Lists notes for one book in reverse chronological order.",
)
def list_notes(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    return [serialize_note(note) for note in sorted(book.notes, key=lambda item: item.created_at, reverse=True)]


@app.patch(
    "/books/{book_id}/notes/{note_id}",
    summary="Update note",
    description="Updates note text, page, or type for one note owned by the authenticated user.",
)
def update_note(
    book_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    _get_book_for_user(db, book_id, user.id)
    note = _get_note_for_user(db, book_id, note_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(note, key, value)
    db.commit()
    db.refresh(note)
    return serialize_note(note)


@app.delete(
    "/books/{book_id}/notes/{note_id}",
    status_code=204,
    summary="Delete note",
    description="Deletes one note owned by the authenticated user.",
)
def delete_note(
    book_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    _get_book_for_user(db, book_id, user.id)
    note = _get_note_for_user(db, book_id, note_id, user.id)
    db.delete(note)
    db.commit()


@app.post(
    "/books/{book_id}/notes/photo",
    status_code=201,
    summary="AI OCR note from photo",
    description="Extracts note text from a photo using Tesseract or EasyOCR for handwritten input.",
)
def create_note_from_photo(
    book_id: int,
    image: Annotated[bytes | None, Body(media_type="application/octet-stream")] = None,
    page: int | None = None,
    is_handwritten: bool = False,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    if not image:
        raise HTTPException(status_code=400, detail="Upload image bytes as application/octet-stream")
    text = extract_text_from_image(image, is_handwritten=is_handwritten)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract note text from the image")
    return create_note(book_id, NoteIn(text=text, page=page, note_type="handwritten_photo"), db=db, user=user)


@app.post(
    "/books/{book_id}/notes/voice",
    status_code=201,
    summary="AI voice note",
    description="Transcribes an audio note and stores it for a book.",
)
def create_note_from_voice(
    book_id: int,
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    page: int | None = None,
    audio_format: str = "wav",
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    text = transcribe_audio(audio, suffix=f".{audio_format.strip('.')}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe audio")
    return create_note(book_id, NoteIn(text=text, page=page, note_type="voice"), db=db, user=user)


@app.post(
    "/books/photo/recognize",
    summary="AI book recognition from photo",
    description="Extracts text from a book photo and searches Google Books for matches.",
)
def recognize_book_photo(
    image: Annotated[bytes | None, Body(media_type="application/octet-stream")] = None,
    is_handwritten: bool = False,
):
    if not image:
        raise HTTPException(status_code=400, detail="Upload image bytes as application/octet-stream")
    text = extract_text_from_image(image, is_handwritten=is_handwritten)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the image")
    matches = _lookup_google_matches(text[:120], limit=5)
    return {"ocr_text": text, "matches": matches}




def handle_image_upload(image_filepath: str, is_handwritten: bool = False):
    """
    Reads the uploaded image, passes it to the OCR module,
    and uses the result to search or populate details.
    """
    try:
        # Read the image as bytes (since your ocr.py expects image_bytes)
        with open(image_filepath, "rb") as image_file:
            img_bytes = image_file.read()

        # Call your existing function
        extracted_text = extract_text_from_image(img_bytes, is_handwritten=is_handwritten)

        if not extracted_text:
            print("No text could be extracted from the image.")
            return None

        print(f"Extracted Text: {extracted_text}")

        # --- Point 2a: Automatically search based on text ---
        # results = search_books(extracted_text, my_book_database)
        # if results:
        #     update_ui_with_search_results(results)

        # --- Point 2b: Populate details ---
        # else:
        #     ui_details_field.set_text(extracted_text)

        return extracted_text

    except RuntimeError as e:
        # This will catch your specific Tesseract error messages
        print(f"OCR Error: {e}")


@app.post(
    "/books/voice/recognize",
    summary="AI book recognition from voice",
    description="Transcribes voice input and searches Google Books for matching books.",
)
def recognize_book_voice(
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    audio_format: str = "wav",
):
    text = transcribe_audio(audio, suffix=f".{audio_format.strip('.')}")
    errors = []
    try:
        matches = _google_books_search(text, limit=5) if text.strip() else []
    except requests.RequestException as exc:
        matches = []
        errors.append(f"Google Books lookup failed: {exc}")
    result = {"transcript": text, "matches": matches}
    if errors:
        result["errors"] = errors
    return result


@app.post(
    "/books/{book_id}/share",
    summary="Create share QR link",
    description="Creates a public share link and QR code URL for one book.",
)
def create_share_link(
    book_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = _get_book_for_user(db, book_id, user.id)
    link = db_models.ShareLink(book_id=book.id, token=token_urlsafe(18))
    db.add(link)
    db.commit()
    db.refresh(link)
    share_url = str(request.url_for("public_shared_book", token=link.token))
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote(share_url)}"
    verified = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == link.token).first() is not None
    return {"token": link.token, "share_url": share_url, "qr_url": qr_url, "verified": verified}


@app.get(
    "/share/{token}",
    name="public_shared_book",
    summary="Open shared book",
    description="Returns a public read-only view of a shared book.",
)
def public_shared_book(token: str, db: Session = Depends(get_db)):
    link = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    return serialize_shared_book(link.book)


@app.get(
    "/suggestions",
    summary="AI book suggestions",
    description="Ranks the user's books with TF-IDF cosine similarity over book descriptions.",
)
def suggestions(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return suggest_books_for_user(db, user)


@app.get(
    "/user/stats",
    summary="User reading statistics",
    description="Returns total read pages, top three genres, and daily progress for the last seven days.",
)
def user_stats(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return build_user_stats(db, user)
