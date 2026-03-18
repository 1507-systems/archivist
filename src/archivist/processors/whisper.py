"""Whisper-based audio transcription (optional dependency)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe_audio(audio_path: Path, model_name: str = "base") -> str:
    """Transcribe an audio file using OpenAI Whisper.

    Requires the 'whisper' optional dependency:
        pip install archivist[whisper]

    Args:
        audio_path: Path to the audio file (MP3, WAV, etc.)
        model_name: Whisper model size (tiny, base, small, medium, large)

    Returns:
        Transcribed text.

    Raises:
        ImportError: If openai-whisper is not installed.
        FileNotFoundError: If the audio file doesn't exist.
    """
    try:
        import whisper
    except ImportError:
        msg = (
            "Whisper transcription requires the 'whisper' extra. "
            "Install with: pip install archivist[whisper]"
        )
        raise ImportError(msg) from None

    if not audio_path.exists():
        msg = f"Audio file not found: {audio_path}"
        raise FileNotFoundError(msg)

    logger.info("Transcribing %s with Whisper model '%s'...", audio_path.name, model_name)
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path))
    text: str = result["text"]
    logger.info("Transcription complete: %d characters", len(text))
    return text
