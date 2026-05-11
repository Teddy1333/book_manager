import subprocess
import shutil
import tempfile
from pathlib import Path

import speech_recognition as sr


SUPPORTED_AUDIO_SUFFIXES = {".wav", ".aiff", ".aif", ".flac"}


def _clean_suffix(suffix: str) -> str:
    suffix = (suffix or ".wav").strip().lower()
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix


def convert_audio_to_wav(audio_bytes: bytes, suffix: str = ".wav") -> bytes:
    if not audio_bytes:
        return b""

    suffix = _clean_suffix(suffix)
    if suffix == ".wav":
        return audio_bytes

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "Audio conversion requires ffmpeg to be installed and available on PATH"
        )

    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as input_file:
            input_file.write(audio_bytes)
            input_path = Path(input_file.name)

        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        output_path = Path(output_file.name)
        output_file.close()

        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown ffmpeg error").strip()
            raise RuntimeError(f"Could not convert audio to wav: {detail}")

        return output_path.read_bytes()
    finally:
        for path in (input_path, output_path):
            if path and path.exists():
                path.unlink()


def transcribe_audio(
    audio_bytes: bytes, suffix: str = ".wav", language: str = "bg-BG"
) -> str:
    if not audio_bytes:
        return ""

    recognizer = sr.Recognizer()
    temp_path = None
    try:
        suffix = _clean_suffix(suffix)
        normalized_audio = (
            audio_bytes
            if suffix in SUPPORTED_AUDIO_SUFFIXES
            else convert_audio_to_wav(audio_bytes, suffix=suffix)
        )

        output_suffix = ".wav" if suffix not in SUPPORTED_AUDIO_SUFFIXES else suffix
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=output_suffix
        ) as temp_file:
            temp_file.write(normalized_audio)
            temp_path = Path(temp_file.name)

        with sr.AudioFile(str(temp_path)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language=language).strip()
    except sr.UnknownValueError:
        return ""
    except Exception as exc:
        raise RuntimeError(f"Could not transcribe audio: {exc}") from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
