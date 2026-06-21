import json
import os

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

router = APIRouter()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


class BookForSuggestion(BaseModel):
    id: int
    title: str | None = None
    author: str | None = None
    description: str | None = None
    tags: list[str] = []


@router.post("/suggest")
async def suggest(books: list[BookForSuggestion], limit: int = 5) -> list[dict]:
    if not books:
        return []

    # Collect all tags for preference analysis
    all_tags = []
    for b in books:
        all_tags.extend(b.tags)
    tag_summary = ""
    if all_tags:
        from collections import Counter
        top_tags = Counter(all_tags).most_common(10)
        tag_summary = f"\nTheir most common genres/tags (by frequency): {', '.join(f'{tag} ({count})' for tag, count in top_tags)}\n"

    # Build a summary of the user's library
    library_summary = "\n".join(
        f"- {b.title or 'Untitled'} by {b.author or 'Unknown'}"
        + (f" [tags: {', '.join(b.tags)}]" if b.tags else "")
        + (f" — {b.description[:100]}..." if b.description and len(b.description) > 100 else f" — {b.description}" if b.description else "")
        for b in books
    )

    prompt = (
        f"Based on this person's book library and reading preferences, suggest {limit} NEW books they would enjoy. "
        "These must be real books that actually exist — not ones already in their library. "
        "Pay close attention to their preferred genres/tags when making suggestions.\n\n"
        f"Their library:\n{library_summary}\n"
        f"{tag_summary}\n"
        f"Return a JSON object with key \"suggestions\" containing an array of {limit} objects, each with:\n"
        "- title (string): the book title\n"
        "- author (string): the author name\n"
        "- reason (string): one short sentence explaining why they'd like it based on their reading patterns\n"
    )

    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        return result.get("suggestions", [])[:limit]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Suggestion generation failed: {exc}")
