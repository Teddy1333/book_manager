"""Abstract base class for book scrapers.

To add a new scraper:
1. Create a new file in services/ (e.g. services/my_scraper.py)
2. Implement a class that extends BookScraper
3. Register it in services/registry.py
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class BookResult:
    """Standardized book result returned by all scrapers."""
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pages: str | None = None
    description: str | None = None
    cover_url: str | None = None
    categories: str | None = None
    year: str | None = None
    language: str | None = None
    url: str | None = None
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "isbn": self.isbn,
            "publisher": self.publisher,
            "pages": self.pages,
            "description": self.description,
            "cover_url": self.cover_url,
            "categories": self.categories,
            "year": self.year,
            "language": self.language,
            "url": self.url,
            "source": self.source,
        }


class BookScraper(ABC):
    """Abstract base class for all book scrapers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this scraper (e.g. 'helikon', 'chitanka')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g. 'Helikon.bg', 'Chitanka.info')."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[BookResult]:
        """Search for books matching the query. Returns a list of BookResult."""
        ...
