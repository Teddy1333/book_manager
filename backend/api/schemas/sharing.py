from pydantic import BaseModel


class ShareImportIn(BaseModel):
    url: str | None = None
    token: str | None = None
