from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from services.ocr import extract_text_from_image, ocr_status

router = APIRouter()


@router.get("/status")
def status():
    return ocr_status()


@router.post("/ocr")
def ocr(
    image: Annotated[bytes, Body(media_type="application/octet-stream")],
    is_handwritten: bool = False,
):
    if not image:
        raise HTTPException(status_code=400, detail="Image bytes required")
    try:
        text = extract_text_from_image(image, is_handwritten=is_handwritten)
        return {"text": text}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
