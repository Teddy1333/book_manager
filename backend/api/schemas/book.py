from pydantic import BaseModel, Field, field_validator

from utils import normalize_isbn


class BookIn(BaseModel):
    title: str = Field(min_length=1)
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pages: str | None = None
    description: str | None = None
    cover_url: str | None = None
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_isbn(value)
        if normalized and len(normalized) not in {10, 13}:
            raise ValueError("ISBN must contain 10 or 13 digits")
        return normalized or None


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    pages: str | None = None
    description: str | None = None
    cover_url: str | None = None
    tags: list[str] | None = None

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_isbn(value)
        if normalized and len(normalized) not in {10, 13}:
            raise ValueError("ISBN must contain 10 or 13 digits")
        return normalized or None
