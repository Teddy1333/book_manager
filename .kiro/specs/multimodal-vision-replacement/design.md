# Design Document

## Overview

This document describes the architecture for replacing the OCR-based image extraction in the AI service with a multimodal vision model endpoint. The design covers the new `/vision` endpoint, OpenAI API integration, scraper-based enrichment, and removal of all legacy OCR code and dependencies.

## Architecture

The change is scoped to the `backend/ai/` service. The existing OCR router/service modules are deleted and replaced by a new vision router and service. The vision service uses the `openai` Python client to send images to a multimodal model and parse structured book metadata from the response. After extraction, the service calls the scraper service (`backend/scraper/`) for enrichment via HTTP.

```
┌─────────────────────────────────────────────────────────────┐
│                       AI Service (port 8001)                 │
│                                                             │
│  ┌──────────────┐   ┌──────────────────┐                   │
│  │ POST /vision │──▶│  VisionService    │                   │
│  │  (router)    │   │                  │                   │
│  └──────────────┘   │  ┌────────────┐  │   ┌────────────┐ │
│                     │  │ OpenAI API │  │   │ httpx call │ │
│                     │  │  client    │  │──▶│ to scraper │ │
│                     │  └────────────┘  │   │ /search    │ │
│                     └──────────────────┘   └────────────┘ │
│                                                             │
│  ┌──────────────┐   ┌──────────────────┐                   │
│  │ POST /speech │──▶│  SpeechService   │  (unchanged)      │
│  └──────────────┘   └──────────────────┘                   │
│                                                             │
│  ┌───────────────────┐   ┌─────────────────┐               │
│  │ POST /suggestions │──▶│ TF-IDF logic    │ (unchanged)   │
│  └───────────────────┘   └─────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Vision Router (`routers/vision.py`)

Handles HTTP request validation and delegates to the vision service.

```python
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from services.vision import extract_book_metadata

router = APIRouter()


@router.post("/vision")
async def vision(
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
):
    if not image:
        raise HTTPException(status_code=400, detail="Image bytes required")
    return await extract_book_metadata(image)
```

### 2. Vision Service (`services/vision.py`)

Encapsulates OpenAI API interaction and scraper enrichment logic.

```python
import base64
import os

import httpx
from openai import AsyncOpenAI

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
SCRAPER_SERVICE_URL = os.environ.get("SCRAPER_SERVICE_URL", "http://scraper:8002")
VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


async def _call_vision_model(image_bytes: bytes) -> dict:
    """Send image to vision model, return extracted Book_Metadata dict."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = await client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract the following book metadata from this image. "
                            "Return a JSON object with keys: title, author, isbn, description. "
                            "Use null for any field you cannot determine."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
    )
    # Parse the JSON response from the model
    import json
    content = response.choices[0].message.content
    return json.loads(content)


async def _enrich_via_scraper(metadata: dict) -> tuple[list | None, bool]:
    """Call scraper service to enrich metadata. Returns (results, success)."""
    query = metadata.get("title") or metadata.get("author")
    if not query:
        return None, False

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.get(
                f"{SCRAPER_SERVICE_URL}/search",
                params={"q": query, "limit": 3},
            )
            resp.raise_for_status()
            return resp.json(), True
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, False


async def extract_book_metadata(image_bytes: bytes) -> dict:
    """Full pipeline: extract via vision model, then enrich via scraper."""
    try:
        raw_metadata = await _call_vision_model(image_bytes)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Vision model error: {exc}")

    # Normalize to ensure all four fields exist
    metadata = {
        "title": raw_metadata.get("title"),
        "author": raw_metadata.get("author"),
        "isbn": raw_metadata.get("isbn"),
        "description": raw_metadata.get("description"),
    }

    # Enrichment step
    has_query = metadata["title"] is not None or metadata["author"] is not None
    enrichment_results = None
    enriched = False

    if has_query:
        enrichment_results, enriched = await _enrich_via_scraper(metadata)

    return {
        **metadata,
        "enrichment": enrichment_results,
        "enriched": enriched,
    }
```

### 3. Configuration Module (`services/config.py`)

Validates environment variables at import time, causing startup failure if `OPENAI_API_KEY` is missing.

```python
import os
import sys


def validate_config():
    """Validate required environment variables. Call at module import."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "ERROR: OPENAI_API_KEY environment variable is not set or empty. "
            "The AI service cannot start without it.",
            file=sys.stderr,
        )
        sys.exit(1)
```

### 4. Updated `main.py`

```python
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
```

### 5. Updated Dockerfile

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

Only `ffmpeg` remains (needed by the speech service). All Tesseract/OCR system packages are removed.

### 6. Updated `requirements.txt`

```
fastapi==0.136.1
uvicorn==0.46.0
openai>=1.35.0
httpx>=0.27.0
SpeechRecognition==3.14.5
python-multipart==0.0.20
scikit-learn==1.8.0
scipy==1.17.1
numpy==2.4.4
joblib==1.5.3
threadpoolctl==3.6.0
```

Removed: `pytesseract`, `pillow`. Added: `openai`, `httpx`.

### 7. Updated `docker-compose.yml` (AI service section)

```yaml
  ai:
    build:
      context: ./backend/ai
    ports:
      - "${AI_PORT:-8001}:8001"
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.openai.com/v1}
      SCRAPER_SERVICE_URL: ${SCRAPER_SERVICE_URL:-http://scraper:8002}
    restart: unless-stopped
```

### 8. Updated `.env` (additions)

```dotenv
# ── OpenAI / Vision Model ─────────────────────────────────────────────────────
# API key for the OpenAI-compatible vision model provider.
OPENAI_API_KEY=your-api-key-here
# Base URL for the OpenAI-compatible API. Change to use alternative providers.
OPENAI_BASE_URL=https://api.openai.com/v1
```

## Data Models

### Request

The `/vision` endpoint accepts raw image bytes via `application/octet-stream` content type (same pattern as the former `/ocr` endpoint).

### Response Schema

```python
from pydantic import BaseModel


class BookMetadata(BaseModel):
    title: str | None
    author: str | None
    isbn: str | None
    description: str | None


class VisionResponse(BaseModel):
    title: str | None
    author: str | None
    isbn: str | None
    description: str | None
    enrichment: list | None
    enriched: bool
```

| Field         | Type          | Description                                             |
|---------------|---------------|---------------------------------------------------------|
| `title`       | `str \| None` | Book title extracted by vision model                    |
| `author`      | `str \| None` | Author name extracted by vision model                   |
| `isbn`        | `str \| None` | ISBN extracted by vision model                          |
| `description` | `str \| None` | Book description extracted by vision model              |
| `enrichment`  | `list \| None`| Scraper search results (list of book dicts) or null     |
| `enriched`    | `bool`        | Whether enrichment was performed successfully           |

## Error Handling

| Scenario                          | HTTP Status | Response Body                                      |
|-----------------------------------|-------------|----------------------------------------------------|
| Empty image (0 bytes)             | 400         | `{"detail": "Image bytes required"}`               |
| Vision model API failure/timeout  | 503         | `{"detail": "Vision model error: <description>"}` |
| Scraper unreachable/error         | 200         | Normal response with `enriched: false`, `enrichment: null` |
| Missing OPENAI_API_KEY at startup | N/A         | Service fails to start, logs error to stderr       |

## Files to Delete

| File                                  | Reason                          |
|---------------------------------------|----------------------------------|
| `backend/ai/routers/ocr.py`          | OCR router no longer needed     |
| `backend/ai/services/ocr.py`         | OCR service no longer needed    |
| `backend/ai/requirements-ocr.txt`    | EasyOCR dependency file removed |

## Testing Strategy

- **Property-based tests**: Validate universal properties of the vision service logic (response structure, enrichment trigger conditions, graceful degradation). Use mocked OpenAI client and mocked scraper HTTP calls to test pure logic at high iteration counts.
- **Unit tests**: Specific examples for error cases (empty image → 400, API failure → 503), configuration validation (missing API key → startup failure), and default URL fallback.
- **Integration tests**: Verify endpoint accepts JPEG/PNG/WebP formats, confirm OCR routes return 404, validate docker-compose environment variable passing.
- **Smoke tests**: Confirm deleted files don't exist, requirements.txt has correct packages, Dockerfile doesn't contain OCR system packages.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Response structure completeness

*For any* response from the vision model (whether it contains all fields, some fields, or no identifiable fields), the Vision_Endpoint SHALL return a JSON object containing exactly the four Book_Metadata keys (`title`, `author`, `isbn`, `description`), with `null` for any field the model could not identify.

**Validates: Requirements 1.3, 1.4**

### Property 2: Enrichment trigger condition

*For any* extracted Book_Metadata, the AI_Service SHALL call the Scraper_Service if and only if at least one of `title` or `author` is non-null. When both are null, the scraper is never called.

**Validates: Requirements 3.1, 3.4**

### Property 3: Enrichment merge preserves original metadata

*For any* successful enrichment, the Vision_Endpoint response SHALL contain both the originally extracted Book_Metadata fields unchanged and the enrichment data from the Scraper_Service — the enrichment process never modifies the originally extracted values.

**Validates: Requirements 3.2**

### Property 4: Graceful degradation on scraper failure

*For any* extracted Book_Metadata and any scraper failure (timeout, connection error, HTTP error), the Vision_Endpoint SHALL return the originally extracted Book_Metadata without modification, with `enriched` set to `false` and `enrichment` set to `null`, and SHALL NOT return an error HTTP status.

**Validates: Requirements 3.3**

### Property 5: Enrichment status accuracy

*For any* Vision_Endpoint response, the `enriched` field SHALL be `true` if and only if the Scraper_Service was called and returned a successful response with data. In all other cases (scraper not called, scraper failed, scraper returned error), `enriched` SHALL be `false`.

**Validates: Requirements 3.5**
