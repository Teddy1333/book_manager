"""Scraper registry — manages enabled scrapers.

To add a new scraper:
1. Create a class that extends BookScraper in services/
2. Import and add it to ENABLED_SCRAPERS below
"""

from services.base import BookResult, BookScraper
from services.helikon import HelikonScraper

# ─── Enabled Scrapers ─────────────────────────────────────────────────────────
# Add new scraper instances here to enable them.
# Order matters: scrapers are queried in this order.
ENABLED_SCRAPERS: list[BookScraper] = [
    HelikonScraper(),
]


def get_scrapers() -> list[BookScraper]:
    """Return all enabled scraper instances."""
    return ENABLED_SCRAPERS


def search_all(query: str, limit: int = 5) -> list[dict]:
    """Search across all enabled scrapers, returning combined results.

    Tries each scraper in order. Returns results from the first scraper
    that returns non-empty results.
    """
    for scraper in ENABLED_SCRAPERS:
        try:
            results = scraper.search(query, limit=limit)
            if results:
                return [r.to_dict() for r in results]
        except Exception:
            continue
    return []


def search_by_name(scraper_name: str, query: str, limit: int = 5) -> list[dict]:
    """Search using a specific scraper by name."""
    for scraper in ENABLED_SCRAPERS:
        if scraper.name == scraper_name:
            results = scraper.search(query, limit=limit)
            return [r.to_dict() for r in results]
    raise ValueError(f"Scraper '{scraper_name}' not found. Available: {[s.name for s in ENABLED_SCRAPERS]}")


def list_scrapers() -> list[dict]:
    """Return info about all enabled scrapers."""
    return [{"name": s.name, "display_name": s.display_name} for s in ENABLED_SCRAPERS]
