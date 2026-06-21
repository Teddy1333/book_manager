from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.book_service import get_book_for_user
from services.note_service import get_note_for_user, serialize_note
from services.search_service import ai_ocr, ai_transcribe
from schemas.note import NoteIn, NoteUpdate

router = APIRouter(tags=["notes"])


@router.post("/books/{book_id}/notes", status_code=201, summary="Add note")
def create_note(
    book_id: int,
    payload: NoteIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
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


@router.get("/books/{book_id}/notes", summary="List notes")
def list_notes(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
    return [
        serialize_note(note)
        for note in sorted(book.notes, key=lambda item: item.created_at, reverse=True)
    ]


@router.patch("/books/{book_id}/notes/{note_id}", summary="Update note")
def update_note(
    book_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    get_book_for_user(db, book_id, user.id)
    note = get_note_for_user(db, book_id, note_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(note, key, value)
    db.commit()
    db.refresh(note)
    return serialize_note(note)


@router.delete("/books/{book_id}/notes/{note_id}", status_code=204, summary="Delete note")
def delete_note(
    book_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    get_book_for_user(db, book_id, user.id)
    note = get_note_for_user(db, book_id, note_id, user.id)
    db.delete(note)
    db.commit()


@router.post("/books/{book_id}/notes/photo", status_code=201, summary="AI OCR note from photo")
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
    text = ai_ocr(image, is_handwritten=is_handwritten)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract note text from the image")
    return create_note(
        book_id,
        NoteIn(text=text, page=page, note_type="handwritten_photo"),
        db=db,
        user=user,
    )


@router.post("/books/{book_id}/notes/voice", status_code=201, summary="AI voice note")
def create_note_from_voice(
    book_id: int,
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    page: int | None = None,
    audio_format: str = "wav",
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    text = ai_transcribe(audio, suffix=f".{audio_format.strip('.')}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe audio")
    return create_note(
        book_id,
        NoteIn(text=text, page=page, note_type="voice"),
        db=db,
        user=user,
    )
