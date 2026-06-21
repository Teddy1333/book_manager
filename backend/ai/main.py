from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import ocr, speech, suggestions

app = FastAPI(
    title="Book Diary — AI Service",
    description="OCR (Tesseract), speech transcription, and TF-IDF book suggestions.",
    version="1.0.0",
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


app.include_router(ocr.router)
app.include_router(speech.router)
app.include_router(suggestions.router)
