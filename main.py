from collections import defaultdict
from datetime import UTC, datetime, timedelta
from os import getenv
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import quote

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

from ai.ocr import extract_text_from_image
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


def normalize_isbn(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isdigit() or ch == "X")


def _pages_as_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _get_book_for_user(db: Session, book_id: int, user_id: int) -> db_models.Book:
    book = (
        db.query(db_models.Book)
        .filter(db_models.Book.id == book_id, db_models.Book.owner_id == user_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


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


def _google_books_search(query: str, limit: int = 5) -> list[dict]:
    response = requests.get(
        "https://www.googleapis.com/books/v1/volumes",
        params={"q": query, "maxResults": limit},
        timeout=10,
    )
    response.raise_for_status()
    results = []
    for item in response.json().get("items", []):
        info = item.get("volumeInfo", {})
        identifiers = info.get("industryIdentifiers", [])
        isbn = next(
            (entry.get("identifier") for entry in identifiers if entry.get("type") in {"ISBN_13", "ISBN_10"}),
            None,
        )
        results.append(
            {
                "title": info.get("title"),
                "author": ", ".join(info.get("authors", [])) or None,
                "isbn": normalize_isbn(isbn) or None,
                "publisher": info.get("publisher"),
                "pages": str(info.get("pageCount")) if info.get("pageCount") else None,
                "description": info.get("description"),
                "cover_url": info.get("imageLinks", {}).get("thumbnail"),
                "source": "google_books",
                "tags": info.get("categories", []),
            }
        )
    return results


def _helikon_search(query: str, limit: int = 5) -> list[dict]:
    import importlib

    scraper = importlib.import_module("scraper.helikon_scraper")
    return scraper.search_books(query, limit=limit)


def _search_isbn(db: Session, isbn: str, limit: int = 5) -> dict:
    isbn = normalize_isbn(isbn)
    local_books = (
        db.query(db_models.Book)
        .filter(db_models.Book.isbn == isbn)
        .order_by(db_models.Book.title)
        .all()
    )
    if local_books:
        return {"source": "local", "matches": [serialize_book(book) for book in local_books]}

    google_matches = _google_books_search(f"isbn:{isbn}", limit=limit)
    if google_matches:
        return {"source": "google_books", "matches": google_matches}

    helikon_matches = _helikon_search(isbn, limit=limit)
    return {"source": "helikon" if helikon_matches else "none", "matches": helikon_matches}


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
    return _google_books_search(q, limit=limit)


@app.get(
    "/lookup/isbn/{isbn}",
    summary="Search by ISBN",
    description="Looks for an ISBN locally first, then Google Books, then Helikon.",
)
def lookup_isbn(isbn: str, db: Session = Depends(get_db)):
    return _search_isbn(db, isbn, limit=5)


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
    matches = _google_books_search(q, limit=1)
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
    result = _search_isbn(db, normalized, limit=1)
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


@app.post(
    "/books/{book_id}/notes/photo",
    status_code=201,
    summary="AI OCR note from photo",
    description="Extracts note text from a photo using Tesseract or EasyOCR for handwritten input.",
)
def create_note_from_photo(
    book_id: int,
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    page: int | None = None,
    is_handwritten: bool = False,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
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
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    is_handwritten: bool = False,
):
    text = extract_text_from_image(image, is_handwritten=is_handwritten)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the image")
    matches = _google_books_search(text[:120], limit=5)
    return {"ocr_text": text, "matches": matches}


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
    matches = _google_books_search(text, limit=5) if text.strip() else []
    return {"transcript": text, "matches": matches}


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
    return serialize_book(link.book)


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

