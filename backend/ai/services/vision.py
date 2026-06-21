import base64
import json
import os

import httpx
from fastapi import HTTPException
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


async def extract_text(image_bytes: bytes, is_handwritten: bool = False) -> str:
    """Use the configured vision model to extract text from an image.

    Uses the same OpenAI-compatible client (works with Gemini, OpenAI, etc).
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    if is_handwritten:
        prompt = (
            "This image contains handwritten text in Bulgarian or English. "
            "Transcribe ALL handwritten text you can see, exactly as written. "
            "Preserve the original language (Bulgarian or English). "
            "Output ONLY the transcribed text with no commentary or explanation."
        )
    else:
        prompt = (
            "This image contains printed text in Bulgarian or English. "
            "Transcribe ALL visible text from this image exactly as it appears. "
            "Preserve the original language (Bulgarian or English). "
            "Output ONLY the transcribed text with no commentary or explanation."
        )
    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vision model error: {exc}")


async def extract_page_number(image_bytes: bytes) -> int | None:
    """Use vision model to identify the page number from a book page image."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is a photo of a book page. "
                                "What is the page number? Page numbers are typically "
                                "printed at the top or bottom of the page, in the header or footer area. "
                                "Return ONLY a JSON object: {\"page_number\": N} where N is the integer page number. "
                                "If you cannot find a page number, return {\"page_number\": null}."
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
        content = response.choices[0].message.content
        result = json.loads(content)
        page = result.get("page_number")
        return int(page) if page is not None else None
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Vision model error: {exc}")
