from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from database import db_models
from utils import pages_as_int


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
    totals = {start_date + timedelta(days=i): 0 for i in range(days)}

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
        total = entry.total_pages if entry else pages_as_int(book.pages)
        if entry and total and entry.current_page >= total:
            completed_books += 1

    tag_pages: dict[str, int] = defaultdict(int)
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
