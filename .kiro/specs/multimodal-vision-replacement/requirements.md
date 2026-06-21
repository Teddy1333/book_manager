# Requirements Document

## Introduction

Replace the existing OCR-based image text extraction (Tesseract/EasyOCR) in the AI service with a multimodal vision model endpoint that extracts structured book metadata from images. The new `/vision` endpoint uses the OpenAI API (with configurable base URL) to analyze book cover or page images, returning structured fields such as title, author, ISBN, and description. After extraction, the service automatically attempts enrichment by looking up the book via the existing scraper service. All legacy OCR code and dependencies are removed.

## Glossary

- **AI_Service**: The standalone FastAPI application running on port 8001 in the `backend/ai/` directory, responsible for AI-powered features including vision extraction, speech transcription, and TF-IDF suggestions.
- **Vision_Endpoint**: The new `/vision` HTTP POST endpoint on the AI_Service that accepts an image and returns structured book metadata.
- **Vision_Model**: The OpenAI-compatible multimodal model accessed via the OpenAI API client, used to analyze images and extract structured data.
- **Scraper_Service**: The standalone FastAPI application running on port 8002 in the `backend/scraper/` directory, providing book search functionality via Helikon.bg.
- **Book_Metadata**: A structured data object containing fields: title, author, isbn, and description extracted from a book image.
- **Enrichment**: The process of looking up extracted Book_Metadata via the Scraper_Service to validate and supplement the extracted fields with additional data.
- **OPENAI_API_KEY**: Environment variable holding the API key for authenticating with the OpenAI-compatible vision model provider.
- **OPENAI_BASE_URL**: Environment variable holding the base URL for the OpenAI-compatible API, allowing use of alternative providers.

## Requirements

### Requirement 1: Vision Endpoint Creation

**User Story:** As a user, I want to upload a book cover or page image and receive structured metadata, so that I can quickly add books to my collection without manual data entry.

#### Acceptance Criteria

1. THE Vision_Endpoint SHALL accept HTTP POST requests with an image payload in common image formats (JPEG, PNG, WebP).
2. WHEN the Vision_Endpoint receives a valid image, THE AI_Service SHALL send the image to the Vision_Model for structured metadata extraction.
3. WHEN the Vision_Model returns a successful response, THE Vision_Endpoint SHALL return a JSON response containing Book_Metadata fields: title, author, isbn, and description.
4. WHEN the Vision_Model cannot identify one or more metadata fields from the image, THE Vision_Endpoint SHALL return null for each unidentifiable field in the Book_Metadata response.
5. IF the uploaded image is empty or has zero bytes, THEN THE Vision_Endpoint SHALL return an HTTP 400 error with a descriptive message.
6. IF the Vision_Model API call fails or times out, THEN THE Vision_Endpoint SHALL return an HTTP 503 error with a descriptive message.

### Requirement 2: Legacy OCR Removal

**User Story:** As a developer, I want the old OCR code and dependencies removed, so that the codebase is simpler and the Docker image is smaller without unused Tesseract/EasyOCR/Pillow packages.

#### Acceptance Criteria

1. THE AI_Service SHALL NOT include the `pytesseract`, `pillow`, or `easyocr` packages in its dependency files.
2. THE AI_Service SHALL NOT contain the OCR router module (`routers/ocr.py`) or OCR service module (`services/ocr.py`).
3. THE AI_Service SHALL NOT expose the `/ocr` or `/status` endpoints that were previously provided by the OCR router.
4. THE AI_Service Dockerfile SHALL NOT install Tesseract OCR system packages.
5. THE AI_Service SHALL NOT include the `requirements-ocr.txt` file.

### Requirement 3: Post-Extraction Enrichment

**User Story:** As a user, I want the system to automatically look up books after extracting metadata from an image, so that I get the most complete and accurate book information possible.

#### Acceptance Criteria

1. WHEN the Vision_Model successfully extracts Book_Metadata with a non-null title or author, THE AI_Service SHALL call the Scraper_Service search endpoint using the extracted title or author as the query.
2. WHEN the Scraper_Service returns matching results, THE Vision_Endpoint SHALL merge the enrichment data into the response alongside the originally extracted Book_Metadata.
3. IF the Scraper_Service is unreachable or returns an error, THEN THE Vision_Endpoint SHALL return the originally extracted Book_Metadata without enrichment data and without failing the request.
4. IF the Vision_Model extraction yields null for both title and author, THEN THE AI_Service SHALL skip the enrichment step and return only the extracted Book_Metadata.
5. THE Vision_Endpoint response SHALL include a field indicating whether enrichment was performed successfully.

### Requirement 4: OpenAI API Configuration

**User Story:** As a developer, I want the OpenAI API key and base URL configured via environment variables, so that the service can connect to any OpenAI-compatible provider without code changes.

#### Acceptance Criteria

1. THE AI_Service SHALL read the `OPENAI_API_KEY` environment variable to authenticate with the Vision_Model provider.
2. THE AI_Service SHALL read the `OPENAI_BASE_URL` environment variable to determine the API endpoint for the Vision_Model provider.
3. IF the `OPENAI_API_KEY` environment variable is not set or is empty, THEN THE AI_Service SHALL fail to start and log a clear error message indicating the missing configuration.
4. IF the `OPENAI_BASE_URL` environment variable is not set, THEN THE AI_Service SHALL use the default OpenAI API URL (`https://api.openai.com/v1`).
5. THE docker-compose configuration SHALL pass `OPENAI_API_KEY` and `OPENAI_BASE_URL` from the host `.env` file into the AI_Service container as environment variables.
6. THE `.env` file SHALL contain placeholder entries for `OPENAI_API_KEY` and `OPENAI_BASE_URL` with descriptive comments.

### Requirement 5: Dependency and Build Updates

**User Story:** As a developer, I want the AI service dependencies updated to include the OpenAI client library and remove OCR packages, so that the service builds correctly with the new vision functionality.

#### Acceptance Criteria

1. THE AI_Service `requirements.txt` SHALL include the `openai` Python package.
2. THE AI_Service `requirements.txt` SHALL NOT include `pytesseract` or `pillow` packages.
3. THE AI_Service `requirements.txt` SHALL include the `httpx` package for making internal HTTP calls to the Scraper_Service.
4. THE AI_Service Dockerfile SHALL NOT install system-level OCR dependencies (tesseract-ocr, leptonica, language data packages).
