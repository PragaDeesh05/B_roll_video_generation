"""
Text-to-Speech Service with modular adapters, multilingual support (en, hi, ta), and deterministic fallback.
"""
from __future__ import annotations

import abc
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Union

from app.config import settings

logger = logging.getLogger(__name__)

LANGUAGE_VOICE_MAP = {
    "en": "en-US-ChristopherNeural",
    "hi": "hi-IN-MadhurNeural",
    "ta": "ta-IN-ValluvarNeural",
}

LANGUAGE_GTTS_MAP = {
    "en": "en",
    "hi": "hi",
    "ta": "ta",
}


class BaseTTSAdapter(abc.ABC):
    """Abstract base class for TTS adapters."""

    @abc.abstractmethod
    def synthesize(
        self, text: str, output_path: Path, voice: Optional[str] = None, language: str = "en"
    ) -> Path:
        pass


class DeterministicMockTTSAdapter(BaseTTSAdapter):
    """Generates audio with FFmpeg without network access or heavy TTS runtimes."""

    def synthesize(
        self, text: str, output_path: Path, voice: Optional[str] = None, language: str = "en"
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Calculate realistic duration: approx 0.38s per word for en, ~0.45s for hi/ta, minimum 3.0s
        words = text.split()
        pace = 0.45 if language in ("hi", "ta") else 0.38
        duration = max(3.0, round(len(words) * pace, 1))
        wav_path = output_path.with_suffix(".wav")

        # Generate sine tone using FFmpeg lavfi
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"sine=frequency=440:duration={duration}",
                "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(wav_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return wav_path


class EdgeTTSAdapter(BaseTTSAdapter):
    """High-quality Microsoft Azure neural voices via edge-tts."""

    def synthesize(
        self, text: str, output_path: Path, voice: Optional[str] = None, language: str = "en"
    ) -> Path:
        import edge_tts

        selected_voice = voice or LANGUAGE_VOICE_MAP.get(language, "en-US-ChristopherNeural")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path = output_path.with_suffix(".mp3")

        async def _run():
            communicate = edge_tts.Communicate(text, selected_voice)
            await asyncio.wait_for(communicate.save(str(mp3_path)), timeout=10.0)

        asyncio.run(_run())

        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            raise RuntimeError(f"edge-tts produced empty output for voice '{selected_voice}'")

        return mp3_path


class GttsAdapter(BaseTTSAdapter):
    """Google Text-to-Speech adapter."""

    def synthesize(
        self, text: str, output_path: Path, voice: Optional[str] = None, language: str = "en"
    ) -> Path:
        import concurrent.futures
        from gtts import gTTS

        gtts_lang = LANGUAGE_GTTS_MAP.get(language, "en")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path = output_path.with_suffix(".mp3")

        def _save():
            tts = gTTS(text=text, lang=gtts_lang, slow=False)
            tts.save(str(mp3_path))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_save)
            future.result(timeout=10.0)

        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            raise RuntimeError(f"gTTS produced empty output for language '{gtts_lang}'")

        return mp3_path


class Pyttsx3Adapter(BaseTTSAdapter):
    """Offline pyttsx3 synthesizer (English only)."""

    def synthesize(
        self, text: str, output_path: Path, voice: Optional[str] = None, language: str = "en"
    ) -> Path:
        if language != "en":
            raise NotImplementedError("pyttsx3 offline synthesizer only supports English")

        import pyttsx3

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path = output_path.with_suffix(".wav")
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()

        if not wav_path.exists() or wav_path.stat().st_size == 0:
            raise RuntimeError("pyttsx3 produced empty output")

        return wav_path


class TTSService:
    """TTS service managing adapter selection with graceful multi-tier fallbacks and multilingual support."""

    def __init__(self, adapter: Optional[BaseTTSAdapter] = None) -> None:
        self.adapter = adapter

    def synthesize(
        self,
        text: str,
        output_path: Union[Path, str],
        voice: Optional[str] = None,
        language: str = "en",
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lang = (language or "en").strip().lower()
        if lang not in ("en", "hi", "ta"):
            raise ValueError(
                f"Unsupported TTS language '{language}'. Supported languages: en, hi, ta"
            )

        selected_voice = voice or LANGUAGE_VOICE_MAP.get(lang, "en-US-ChristopherNeural")

        if settings.tts_provider == "mock":
            return DeterministicMockTTSAdapter().synthesize(
                text, output_path, selected_voice, language=lang
            )

        if self.adapter:
            try:
                return self.adapter.synthesize(
                    text, output_path, selected_voice, language=lang
                )
            except Exception as e:
                logger.warning(f"Configured TTS adapter failed: {e}; falling back")

        # Fallback tier 1: gTTS (reliable Google TTS natively supporting en, hi, ta)
        try:
            return GttsAdapter().synthesize(
                text, output_path, selected_voice, language=lang
            )
        except Exception as e1:
            logger.warning(f"gTTS failed for {lang} ({e1}); trying edge-tts")

        # Fallback tier 2: edge-tts (Microsoft Azure neural voices)
        try:
            return EdgeTTSAdapter().synthesize(
                text, output_path, selected_voice, language=lang
            )
        except Exception as e2:
            logger.warning(f"edge-tts failed for {lang} ({e2})")

        # Fallback tier 3: pyttsx3 (English only)
        if lang == "en":
            try:
                return Pyttsx3Adapter().synthesize(
                    text, output_path, selected_voice, language=lang
                )
            except Exception as e3:
                logger.warning(f"pyttsx3 failed ({e3}); using deterministic mock TTS")

        # Fallback tier 4: Deterministic Mock TTS (preserves duration in requested language)
        logger.warning(f"Using deterministic mock TTS for language '{lang}'")
        return DeterministicMockTTSAdapter().synthesize(
            text, output_path, selected_voice, language=lang
        )
