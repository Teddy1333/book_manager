from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from services.speech import transcribe_audio

router = APIRouter()


@router.post("/transcribe")
def transcribe(
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    suffix: str = ".wav",
    language: str = "bg-BG",
):
    if not audio:
        raise HTTPException(status_code=400, detail="Audio bytes required")
    try:
        text = transcribe_audio(audio, suffix=suffix, language=language)
        return {"text": text}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
