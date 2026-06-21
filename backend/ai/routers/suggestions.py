from fastapi import APIRouter
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

router = APIRouter()


class BookForSuggestion(BaseModel):
    id: int
    title: str | None = None
    author: str | None = None
    description: str | None = None
    tags: list[str] = []


def _book_text(book: BookForSuggestion) -> str:
    parts = [book.title or "", book.author or "", book.description or "", " ".join(book.tags)]
    return " ".join(part for part in parts if part).strip()


@router.post("/suggest")
def suggest(books: list[BookForSuggestion], limit: int = 10) -> list[dict]:
    books_with_text = [book for book in books if _book_text(book)]
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
        suggestions.append({
            "book_id": book.id,
            "title": book.title,
            "author": book.author,
            "score": round(float(score), 4),
            "reasons": ["similar description profile"],
        })

    suggestions.sort(key=lambda item: item["score"], reverse=True)
    return suggestions[:limit]
