# Book Diary API

FastAPI backend for managing books, reading progress, OCR-based page tracking, voice notes, public share links, and reading analytics.

## Features

- User signup and JWT login
- Manual book management with tags
- Google Books and Helikon lookup
- ISBN merge flow: local database, Google Books, Helikon
- AI OCR book recognition from photos
- AI voice book recognition
- Manual and OCR-based reading progress
- Manual, handwritten OCR, and voice notes
- TF-IDF cosine similarity recommendations
- Reading statistics and 7-day progress analytics
- Public share links with QR code URLs
- Swagger documentation for all endpoints
- CORS support for a future frontend or mobile app

## Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the API:

```powershell
uvicorn main:app --reload
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

Optional secret key configuration:

```powershell
$env:BOOK_MANAGER_SECRET_KEY="change-this-for-production"
```

## Tesseract OCR

Install Tesseract for Windows and make sure its install folder is available in `PATH`.

Typical install path:

```text
C:\Program Files\Tesseract-OCR
```

Check it from PowerShell:

```powershell
tesseract --version
```

The app uses Tesseract for printed text OCR. For handwritten images, call OCR endpoints with:

```text
is_handwritten=true
```

That path uses EasyOCR. EasyOCR is heavier because it installs deep learning dependencies, so first install all project requirements before using handwritten OCR.

Install the optional handwritten OCR dependency:

```powershell
python -m pip install -r requirements-ocr.txt
```

On Windows, EasyOCR may require Microsoft C++ Build Tools because one of its dependencies can build native wheels. If installation fails with `link.exe not found`, install Visual Studio Build Tools with the C++ workload and retry the command.

## Audio Conversion

Voice endpoints accept WAV directly. Other audio formats require `ffmpeg` in `PATH`.

Check it with:

```powershell
ffmpeg -version
```

## Tests

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The integration test covers:

- Signup
- Login
- Search Book
- Add Book
- Add Progress via Photo
- Duplicate ISBN protection
- ISBN local lookup
- ISBN import
- Tags listing
- User stats
- QR share link verification

## Main Endpoints

- `GET /`
- `GET /health`
- `POST /signup`
- `POST /token`
- `GET /lookup/google`
- `GET /lookup/isbn/{isbn}`
- `GET /lookup/helikon`
- `POST /books`
- `POST /books/import/isbn/{isbn}`
- `GET /tags`
- `POST /books/{book_id}/progress/photo`
- `GET /user/stats`
- `GET /suggestions`
- `POST /books/{book_id}/share`
