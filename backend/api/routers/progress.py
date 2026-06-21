from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.book_service import get_book_for_user
from services.search_service import ai_ocr
from schemas.progress import ProgressIn
from utils import pages_as_int

router = APIRouter(tags=["progress"])


@router.post("/books/{book_id}/progress", status_code=201, summary="Add reading progress")
def add_progress(
    book_id: int,
    payload: ProgressIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
    total_pages = payload.total_pages or pages_as_int(book.pages)
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


@router.post("/books/{book_id}/progress/photo", status_code=201, summary="AI OCR progress from photo")
def add_progress_from_photo(
    book_id: int,
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    is_handwritten: bool = False,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    text = ai_ocr(image, is_handwritten=is_handwritten)
    numbers = [int(part) for part in "".join(ch if ch.isdigit() else " " for ch in text).split()]
    if not numbers:
        raise HTTPException(status_code=422, detail="Could not detect a page number from the image")
    return add_progress(
        book_id,
        ProgressIn(current_page=max(numbers), source="photo"),
        db=db,
        user=user,
    )
