import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.search_service import AI_SERVICE_URL
from services.stats_service import build_user_stats

router = APIRouter(tags=["user"])


@router.get("/user/stats", summary="User reading statistics")
def user_stats(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    return build_user_stats(db, user)


@router.get("/suggestions", summary="AI book suggestions")
def suggestions(
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    books = db.query(db_models.Book).filter(db_models.Book.owner_id == user.id).all()
    book_data = [
        {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "description": book.description,
            "tags": [tag.name for tag in book.tags],
        }
        for book in books
    ]
    try:
        response = httpx.post(f"{AI_SERVICE_URL}/suggest", json=book_data, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return []


@router.get("/ai/status", summary="AI feature status")
def ai_status():
    try:
        response = httpx.get(f"{AI_SERVICE_URL}/status", timeout=5.0)
        return {"ocr": response.json()}
    except httpx.HTTPError:
        return {"ocr": {"available": False, "error": "AI service unavailable"}}
