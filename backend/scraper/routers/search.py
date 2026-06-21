from fastapi import APIRouter, Query

from services.registry import list_scrapers, search_all, search_by_name

router = APIRouter()


@router.get("/search")
def search(
    q: str,
    limit: int = Query(default=5, ge=1, le=10),
    scraper: str | None = Query(default=None, description="Specific scraper to use (e.g. 'helikon')"),
):
    """Search for books across enabled scrapers.

    If `scraper` is specified, only that scraper is used.
    Otherwise, scrapers are tried in order until one returns results.
    """
    if scraper:
        return search_by_name(scraper, q, limit=limit)
    return search_all(q, limit=limit)


@router.get("/scrapers")
def scrapers():
    """List all enabled scrapers."""
    return list_scrapers()
