from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.book_service import (
    create_book,
    ensure_unique_isbn,
    get_book_for_user,
    serialize_book,
    set_tags,
)
from services.share_service import import_shared_book
from schemas.book import BookIn, BookUpdate
from schemas.sharing import ShareImportIn

router = APIRouter(tags=["books"])


@router.post("/books", status_code=201, summary="Add book")
def create_book_route(
    payload: BookIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
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


@router.get("/books", summary="List books")
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


@router.post("/books/import/share", status_code=201, summary="Import shared book")
def import_shared_book_route(
    payload: ShareImportIn,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return import_shared_book(payload, db, user)


@router.get("/books/{book_id}", summary="Get book")
def get_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return serialize_book(get_book_for_user(db, book_id, user.id))


@router.patch("/books/{book_id}", summary="Update book")
def update_book(
    book_id: int,
    payload: BookUpdate,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if "isbn" in data:
        ensure_unique_isbn(db, user.id, data["isbn"], current_book_id=book.id)
    tags = data.pop("tags", None)
    for key, value in data.items():
        setattr(book, key, value)
    if tags is not None:
        set_tags(db, book, tags)
    db.commit()
    db.refresh(book)
    return serialize_book(book)


@router.delete("/books/{book_id}", status_code=204, summary="Delete book")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
    db.delete(book)
    db.commit()


@router.get("/tags", summary="List tags")
def list_tags(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    books = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id).all()
    tag_counts: dict[str, int] = defaultdict(int)
    for book in books:
        for tag in book.tags:
            tag_counts[tag.name] += 1
    return [
        {"name": name, "books_count": count}
        for name, count in sorted(tag_counts.items(), key=lambda item: item[0])
    ]
