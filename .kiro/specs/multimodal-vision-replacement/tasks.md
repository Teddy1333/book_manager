# Implementation Plan: Multimodal Vision Replacement

## Overview

Replace the OCR-based image extraction in the AI service with a multimodal vision model endpoint. This involves creating a new `/vision` endpoint using the OpenAI Python client, adding scraper-based enrichment, removing all legacy OCR code/dependencies, and updating infrastructure files (Dockerfile, docker-compose, .env, requirements.txt).

## Tasks

- [ ] 1. Remove legacy OCR code and dependencies
  - [ ] 1.1 Delete OCR router, service, and requirements file
    - Delete `backend/ai/routers/ocr.py`
    - Delete `backend/ai/services/ocr.py`
    - Delete `backend/ai/requirements-ocr.txt`
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [ ] 1.2 Update `requirements.txt` to remove OCR packages and add new dependencies
    - Remove `pytesseract` and `pillow` from `backend/ai/requirements.txt`
    - Add `openai>=1.35.0` and `httpx>=0.27.0`
    - _Requirements: 2.1, 5.1, 5.2, 5.3_

  - [ ] 1.3 Update Dockerfile to remove Tesseract system packages
    - Remove `tesseract-ocr`, `tesseract-ocr-bul`, `tesseract-ocr-eng` from `apt-get install` in `backend/ai/Dockerfile`
    - Keep `ffmpeg` (needed by speech service)
    - _Requirements: 2.4, 5.4_

- [ ] 2. Implement vision service and router
  - [ ] 2.1 Create configuration validation module (`backend/ai/services/config.py`)
    - Implement `validate_config()` that reads `OPENAI_API_KEY` from environment
    - If key is not set or empty, print error to stderr and call `sys.exit(1)`
    - _Requirements: 4.1, 4.3_

  - [ ] 2.2 Create vision service (`backend/ai/services/vision.py`)
    - Implement `_call_vision_model(image_bytes)` using `AsyncOpenAI` client
    - Base64-encode image and send as `image_url` content in chat completion
    - Use `response_format={"type": "json_object"}` to get structured JSON
    - Parse response into dict with keys: title, author, isbn, description
    - Implement `_enrich_via_scraper(metadata)` using `httpx.AsyncClient`
    - Call scraper `/search` endpoint with title or author as query
    - Implement `extract_book_metadata(image_bytes)` as the full pipeline
    - Normalize response to always include all four Book_Metadata keys (null for missing)
    - On vision model failure, raise HTTPException 503
    - On scraper failure, return metadata with `enriched: false` and `enrichment: null`
    - Read `OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`), `SCRAPER_SERVICE_URL` (default `http://scraper:8002`), and `OPENAI_VISION_MODEL` (default `gpt-4o-mini`) from environment
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.4_

  - [ ] 2.3 Create vision router (`backend/ai/routers/vision.py`)
    - Implement `POST /vision` endpoint accepting raw image bytes (`application/octet-stream`)
    - Validate that image payload is non-empty, return 400 if empty
    - Delegate to `extract_book_metadata` from vision service
    - _Requirements: 1.1, 1.5_

  - [ ]* 2.4 Write property tests for vision service
    - **Property 1: Response structure completeness** — for any vision model output, the response always contains exactly the four Book_Metadata keys with null for missing fields
    - **Property 2: Enrichment trigger condition** — scraper is called if and only if title or author is non-null
    - **Property 3: Enrichment merge preserves original metadata** — enrichment never modifies extracted values
    - **Property 4: Graceful degradation on scraper failure** — on any scraper error, response contains original metadata with enriched=false
    - **Property 5: Enrichment status accuracy** — enriched is true if and only if scraper was called and succeeded
    - Mock `AsyncOpenAI` client and `httpx.AsyncClient` to test pure logic
    - **Validates: Requirements 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5**

  - [ ]* 2.5 Write unit tests for vision endpoint error cases
    - Test empty image → HTTP 400
    - Test vision model API failure → HTTP 503
    - Test config validation: missing OPENAI_API_KEY → sys.exit(1)
    - Test default OPENAI_BASE_URL fallback when env var not set
    - _Requirements: 1.5, 1.6, 4.3, 4.4_

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Update main.py and infrastructure
  - [ ] 4.1 Update `backend/ai/main.py` to register vision router and remove OCR
    - Import and call `validate_config()` from `services.config` before router imports
    - Replace `from routers import ocr` with `from routers import vision`
    - Replace `app.include_router(ocr.router)` with `app.include_router(vision.router)`
    - Update app description and version to reflect vision-based service
    - _Requirements: 2.3, 4.3_

  - [ ] 4.2 Update `docker-compose.yml` AI service section with environment variables
    - Add `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `SCRAPER_SERVICE_URL` environment variables to the `ai` service
    - Update service comment to reflect new functionality
    - _Requirements: 4.5_

  - [ ] 4.3 Update `.env` with OpenAI configuration placeholders
    - Add `OPENAI_API_KEY=your-api-key-here` with descriptive comment
    - Add `OPENAI_BASE_URL=https://api.openai.com/v1` with descriptive comment
    - _Requirements: 4.6_

- [ ] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing AI service codebase

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "4.3"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "4.2"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["2.4", "2.5"] }
  ]
}
```
