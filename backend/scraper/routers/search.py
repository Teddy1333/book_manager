from fastapi import APIRouter, Query

from services.helikon_scraper import search_books

router = APIRouter()


@router.get("/search")
def search(q: str, limit: int = Query(default=5, ge=1, le=10)):
    return search_books(q, limit=limit)
