from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import search

app = FastAPI(
    title="Book Diary — Scraper Service",
    description="Book search via pluggable scrapers (Helikon.bg, etc.).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


app.include_router(search.router)
