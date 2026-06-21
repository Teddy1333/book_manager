from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.config import validate_config

validate_config()

from routers import speech, suggestions, vision

app = FastAPI(
    title="Book Diary — AI Service",
    description="Vision-based book metadata extraction, speech transcription, and TF-IDF suggestions.",
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


app.include_router(vision.router)
app.include_router(speech.router)
app.include_router(suggestions.router)
