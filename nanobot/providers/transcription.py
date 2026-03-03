"""Voice transcription via Groq Whisper API."""

from pathlib import Path

import httpx
from loguru import logger

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(file_path: str | Path, api_key: str) -> str:
    """Transcribe an audio file using Groq's Whisper API. Returns text or "" on failure."""
    path = Path(file_path)
    if not path.exists():
        logger.error("Audio file not found: {}", file_path)
        return ""

    try:
        async with httpx.AsyncClient() as client:
            with open(path, "rb") as f:
                response = await client.post(
                    GROQ_TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (path.name, f, "audio/ogg")},
                    data={"model": "whisper-large-v3-turbo"},
                    timeout=60.0,
                )
            response.raise_for_status()
            text = response.json().get("text", "")
            if text:
                logger.info("Transcribed {}: {}...", path.name, text[:80])
            return text
    except Exception as e:
        logger.error("Transcription failed for {}: {}", path.name, e)
        return ""
