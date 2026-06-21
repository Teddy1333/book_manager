from typing import Annotated

import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.book_service import create_book, ensure_unique_isbn
from services.search_service import (
    ai_ocr,
    ai_transcribe,
    google_books_search,
    helikon_search,
    lookup_google_matches,
    search_books,
)
from schemas.book import BookIn
from utils import normalize_isbn

router = APIRouter(tags=["lookup"])


@router.get("/lookup/google", summary="Search Google Books")
def lookup_google(q: str, limit: int = Query(default=5, ge=1, le=20)):
    return lookup_google_matches(q, limit=limit)


@router.get("/lookup/isbn/{isbn}", summary="Search by ISBN")
def lookup_isbn(isbn: str, db: Session = Depends(get_db)):
    return search_books(db, isbn, limit=5)


@router.get("/lookup/helikon", summary="Search Helikon")
def lookup_helikon(q: str, limit: int = Query(default=5, ge=1, le=10)):
    return helikon_search(q, limit=limit)


@router.post("/books/import/google", status_code=201, summary="Import Google book")
def import_google_book(
    q: str,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    try:
        matches = google_books_search(q, limit=1)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Google Books lookup failed: {exc}") from exc
    if not matches:
        raise HTTPException(status_code=404, detail="No book found")
    payload = BookIn(**matches[0])
    ensure_unique_isbn(db, user.id, payload.isbn)
    return create_book(
        db, user.id,
        title=payload.title,
        author=payload.author,
        isbn=payload.isbn,
        publisher=payload.publisher,
        pages=payload.pages,
        description=payload.description,
        cover_url=payload.cover_url,
        source=payload.source,
        tags=payload.tags,
    )


@router.post("/books/import/isbn/{isbn}", status_code=201, summary="Import book by ISBN")
def import_book_by_isbn(
    isbn: str,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    normalized = normalize_isbn(isbn)
    ensure_unique_isbn(db, user.id, normalized)
    result = search_books(db, normalized, limit=1)
    if not result["matches"]:
        raise HTTPException(status_code=404, detail="No book found")
    payload = BookIn(**result["matches"][0])
    return create_book(
        db, user.id,
        title=payload.title,
        author=payload.author,
        isbn=payload.isbn,
        publisher=payload.publisher,
        pages=payload.pages,
        description=payload.description,
        cover_url=payload.cover_url,
        source=payload.source,
        tags=payload.tags,
    )


@router.post("/books/photo/recognize", summary="AI book recognition from photo")
def recognize_book_photo(
    image: Annotated[bytes | None, Body(media_type="application/octet-stream")] = None,
    is_handwritten: bool = False,
):
    if not image:
        raise HTTPException(status_code=400, detail="Upload image bytes as application/octet-stream")
    text = ai_ocr(image, is_handwritten=is_handwritten)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the image")
    matches = lookup_google_matches(text[:120], limit=5)
    return {"ocr_text": text, "matches": matches}


@router.post("/books/voice/recognize", summary="AI book recognition from voice")
def recognize_book_voice(
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    audio_format: str = "wav",
):
    text = ai_transcribe(audio, suffix=f".{audio_format.strip('.')}")
    errors: list[str] = []
    try:
        matches = google_books_search(text, limit=5) if text.strip() else []
    except requests.RequestException as exc:
        matches = []
        errors.append(f"Google Books lookup failed: {exc}")
    result: dict = {"transcript": text, "matches": matches}
    if errors:
        result["errors"] = errors
    return result
