"""
Phase 2 tests: Audio transcription and TTS adapters.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from app.services.transcription_service import (
    TranscriptionService,
    DeterministicMockSTTAdapter,
    TranscriptionResult,
)
from app.services.tts_service import (
    TTSService,
    DeterministicMockTTSAdapter,
)
from app.utils.media import probe_audio


def test_mock_tts_synthesizes_valid_wav(tmp_path):
    adapter = DeterministicMockTTSAdapter()
    out = tmp_path / "test_tts.wav"
    result_path = adapter.synthesize("Regular savings build lasting wealth and stability.", out)

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    probe = probe_audio(result_path, check_silence=False)
    assert probe["valid"] is True
    assert probe["duration"] >= 3.0


def test_silence_detection(tmp_path):
    silent_wav = tmp_path / "silent.wav"
    # Generate 2 seconds of pure silence
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", "2",
            str(silent_wav)
        ],
        check=True, capture_output=True, timeout=20,
    )

    probe = probe_audio(silent_wav, check_silence=True)
    assert probe["valid"] is False
    assert probe["is_silent"] is True
    assert "silence" in probe["error"].lower()


def test_mock_stt_produces_word_level_segments(tmp_path):
    # Create test tone
    tone_wav = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            str(tone_wav)
        ],
        check=True, capture_output=True, timeout=20,
    )

    adapter = DeterministicMockSTTAdapter(
        mock_text="Disciplined investing creates wealth over time."
    )
    res = adapter.transcribe(tone_wav)
    assert isinstance(res, TranscriptionResult)
    assert len(res.segments) > 0
    assert res.duration >= 5.9

    first_seg = res.segments[0]
    assert "start" in first_seg
    assert "end" in first_seg
    assert "words" in first_seg
    assert len(first_seg["words"]) > 0
    first_word = first_seg["words"][0]
    assert "word" in first_word
    assert "start" in first_word


def test_transcription_service_fallback(tmp_path):
    svc = TranscriptionService(adapter=DeterministicMockSTTAdapter())
    tone_wav = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            str(tone_wav)
        ],
        check=True, capture_output=True, timeout=20,
    )
    result = svc.transcribe(tone_wav)
    assert result.method == "mock"
    assert result.duration >= 3.9
