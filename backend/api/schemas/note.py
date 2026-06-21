from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=0)
    note_type: str = "manual"


class NoteUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    page: int | None = Field(default=None, ge=0)
    note_type: str | None = None
