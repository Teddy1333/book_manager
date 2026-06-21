from io import BytesIO
from pathlib import Path
import shutil

from PIL import Image
import pytesseract


COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract() -> str | None:
    tesseract_path = shutil.which("tesseract")
    if not tesseract_path:
        tesseract_path = next((path for path in COMMON_TESSERACT_PATHS if Path(path).exists()), None)
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    return tesseract_path


def ocr_status() -> dict:
    easyocr_available = False
    try:
        import easyocr  # noqa: F401
        easyocr_available = True
    except ImportError:
        pass

    return {
        "tesseract_available": _configure_tesseract() is not None,
        "easyocr_available": easyocr_available,
        "tesseract_install_hint": (
            "Install Tesseract OCR and add it to PATH, or install it to "
            r"C:\Program Files\Tesseract-OCR\tesseract.exe."
        ),
        "easyocr_install_hint": "Optional handwritten OCR: python -m pip install -r requirements-ocr.txt",
    }


def _extract_with_easyocr(image_bytes: bytes) -> str:
    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError("EasyOCR is not installed") from exc

    reader = easyocr.Reader(["bg", "en"], gpu=False)
    results = reader.readtext(image_bytes, detail=0, paragraph=True)
    return " ".join(part.strip() for part in results if str(part).strip()).strip()


def _extract_with_tesseract(image_bytes: bytes) -> str:
    if not _configure_tesseract():
        raise RuntimeError(
            "Tesseract OCR is not installed. Install Tesseract OCR and add it to PATH, "
            r"or install it to C:\Program Files\Tesseract-OCR\tesseract.exe."
        )
    image = Image.open(BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang="bul+eng").strip()


def extract_text_from_image(image_bytes: bytes, is_handwritten: bool = False) -> str:
    if not image_bytes:
        return ""
    try:
        if is_handwritten:
            try:
                return _extract_with_easyocr(image_bytes)
            except RuntimeError as exc:
                if "EasyOCR is not installed" not in str(exc):
                    raise
                return _extract_with_tesseract(image_bytes)
        return _extract_with_tesseract(image_bytes)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR is not installed. Install Tesseract OCR and add it to PATH, "
            r"or install it to C:\Program Files\Tesseract-OCR\tesseract.exe."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not process image: {exc}") from exc
