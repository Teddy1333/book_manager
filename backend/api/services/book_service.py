from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import db_models
from utils import normalize_isbn, pages_as_int


def get_book_for_user(db: Session, book_id: int, user_id: int) -> db_models.Book:
    book = (
        db.query(db_models.Book)
        .filter(db_models.Book.id == book_id, db_models.Book.owner_id == user_id)
        .first()
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def set_tags(db: Session, book: db_models.Book, tag_names: list[str]) -> None:
    cleaned = sorted({name.strip().lower() for name in tag_names if name.strip()})
    tags = []
    for name in cleaned:
        tag = db.query(db_models.Tag).filter(db_models.Tag.name == name).first()
        if not tag:
            tag = db_models.Tag(name=name)
            db.add(tag)
        tags.append(tag)
    book.tags = tags


def ensure_unique_isbn(
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


def serialize_book(book: db_models.Book) -> dict:
    latest_progress = (
        sorted(book.progress_entries, key=lambda item: item.created_at, reverse=True)[0]
        if book.progress_entries
        else None
    )
    total_pages = latest_progress.total_pages if latest_progress else pages_as_int(book.pages)
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


def create_book(
    db: Session,
    user_id: int,
    *,
    title: str,
    author: str | None = None,
    isbn: str | None = None,
    publisher: str | None = None,
    pages: str | None = None,
    description: str | None = None,
    cover_url: str | None = None,
    source: str = "manual",
    tags: list[str] | None = None,
) -> dict:
    book = db_models.Book(
        title=title,
        author=author,
        isbn=isbn,
        publisher=publisher,
        pages=pages,
        description=description,
        cover_url=cover_url,
        source=source,
        owner_id=user_id,
    )
    set_tags(db, book, tags or [])
    db.add(book)
    db.commit()
    db.refresh(book)
    return serialize_book(book)
