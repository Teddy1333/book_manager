from io import BytesIO

from PIL import Image
import pytesseract


def _extract_with_easyocr(image_bytes: bytes) -> str:
    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError("EasyOCR is not installed") from exc

    reader = easyocr.Reader(["bg", "en"], gpu=False)
    results = reader.readtext(image_bytes, detail=0, paragraph=True)
    return " ".join(part.strip() for part in results if str(part).strip()).strip()


def _extract_with_tesseract(image_bytes: bytes) -> str:
    image = Image.open(BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang="bul+eng").strip()


def extract_text_from_image(image_bytes: bytes, is_handwritten: bool = False) -> str:
    if not image_bytes:
        return ""
    try:
        if is_handwritten:
            return _extract_with_easyocr(image_bytes)
        return _extract_with_tesseract(image_bytes)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR is not installed or not available on PATH") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not process image: {exc}") from exc
