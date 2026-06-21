from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from services.vision import extract_book_metadata, extract_text, extract_page_number

router = APIRouter()


@router.post("/vision")
async def vision(
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
):
    if not image:
        raise HTTPException(status_code=400, detail="Image bytes required")
    return await extract_book_metadata(image)


@router.post("/vision/text")
async def vision_text(
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    is_handwritten: bool = False,
):
    if not image:
        raise HTTPException(status_code=400, detail="Image bytes required")
    text = await extract_text(image, is_handwritten=is_handwritten)
    return {"text": text}


@router.post("/vision/page-number")
async def vision_page_number(
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
):
    if not image:
        raise HTTPException(status_code=400, detail="Image bytes required")
    page = await extract_page_number(image)
    return {"page_number": page}
