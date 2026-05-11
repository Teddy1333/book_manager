from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database import db_models


def _book_text(book: db_models.Book) -> str:
    parts = [
        book.title or "",
        book.author or "",
        book.description or "",
        " ".join(tag.name for tag in book.tags),
    ]
    return " ".join(part for part in parts if part).strip()


def suggest_books_for_user(db: Session, user: db_models.User, limit: int = 10) -> list[dict]:
    user_books = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id).all()
    books_with_text = [book for book in user_books if _book_text(book)]
    if len(books_with_text) < 2:
        return []

    documents = [_book_text(book) for book in books_with_text]
    matrix = TfidfVectorizer(stop_words="english").fit_transform(documents)
    similarities = cosine_similarity(matrix)

    suggestions = []
    for index, book in enumerate(books_with_text):
        related_scores = [
            similarities[index][other_index]
            for other_index in range(len(books_with_text))
            if other_index != index
        ]
        score = max(related_scores) if related_scores else 0
        if score <= 0:
            continue
        suggestions.append(
            {
                "book_id": book.id,
                "title": book.title,
                "author": book.author,
                "score": round(float(score), 4),
                "reasons": ["similar description profile"],
            }
        )

    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[:limit]
