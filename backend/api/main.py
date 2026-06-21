from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import db_models
from database.db_manager import engine
from routers import auth, books, lookup, notes, progress, sharing, user

db_models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Book Diary API",
    description="Backend for book management, AI OCR, voice notes, recommendations, analytics, and sharing.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuntimeError)
def runtime_error_handler(_request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/", summary="API overview")
def api_overview():
    return {
        "name": "Book Diary API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", summary="Health check")
def health_check():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


app.include_router(auth.router)
app.include_router(books.router)
app.include_router(notes.router)
app.include_router(progress.router)
app.include_router(lookup.router)
app.include_router(sharing.router)
app.include_router(user.router)
