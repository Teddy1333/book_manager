from pydantic import BaseModel, Field


class ProgressIn(BaseModel):
    current_page: int = Field(ge=0)
    total_pages: int | None = Field(default=None, ge=1)
    source: str = "manual"
