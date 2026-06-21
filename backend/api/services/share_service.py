from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import db_models
from services.book_service import ensure_unique_isbn, set_tags
from services.note_service import serialize_shared_book
from schemas.sharing import ShareImportIn


def share_token_from_value(value: str | None) -> str:
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


def import_shared_book(payload: ShareImportIn, db: Session, user: db_models.User) -> dict:
    token = share_token_from_value(payload.token or payload.url)
    link = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")

    source = link.book
    ensure_unique_isbn(db, user.id, source.isbn)
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
    set_tags(db, book, [tag.name for tag in source.tags])
    db.add(book)
    db.flush()

    for source_note in sorted(source.notes, key=lambda item: item.created_at):
        db.add(db_models.Note(
            book_id=book.id,
            owner_id=user.id,
            text=source_note.text,
            page=source_note.page,
            note_type=f"shared_{source_note.note_type or 'note'}",
            image_path=source_note.image_path,
            audio_path=source_note.audio_path,
        ))

    db.commit()
    db.refresh(book)
    return serialize_shared_book(book)
