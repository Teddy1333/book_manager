from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import db_models
from services.book_service import serialize_book


def get_note_for_user(db: Session, book_id: int, note_id: int, user_id: int) -> db_models.Note:
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
