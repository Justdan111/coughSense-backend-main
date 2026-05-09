"""Unit tests for app.ml.validator.validate_audio."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ml.validator import validate_audio


FIXTURES = Path(__file__).parent.parent / "fixtures" / "audio"


def test_validate_rejects_too_short():
    is_valid, msg = validate_audio(str(FIXTURES / "too_short.wav"))
    assert is_valid is False
    assert msg is not None
    assert "2 seconds" in msg


def test_validate_rejects_quiet_audio():
    is_valid, msg = validate_audio(str(FIXTURES / "cough_quiet.wav"))
    assert is_valid is False
    assert msg is not None
    assert "quiet" in msg.lower()


def test_validate_rejects_white_noise():
    is_valid, msg = validate_audio(str(FIXTURES / "white_noise.wav"))
    assert is_valid is False
    assert msg is not None
    # Either "noise" or "cough characteristics" — both are valid noise-like rejections.
    assert "noise" in msg.lower() or "cough" in msg.lower()


def test_validate_rejects_low_freq_only():
    """200Hz tone has no 500-4000Hz energy → fails the cough-characteristics check."""
    is_valid, msg = validate_audio(str(FIXTURES / "speech_like.wav"))
    assert is_valid is False
    assert msg is not None


def test_validate_accepts_synthetic_cough():
    """Synthetic burst-of-noise around 1500Hz passes all 4 checks."""
    is_valid, msg = validate_audio(str(FIXTURES / "synthetic_cough.wav"))
    assert is_valid is True, f"expected valid, got: {msg}"
    assert msg is None


def test_validate_handles_unloadable_file(tmp_path: Path):
    import warnings

    bad = tmp_path / "not-audio.wav"
    bad.write_bytes(b"this is not a wav file")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # librosa falls back through audioread, noisy
        is_valid, msg = validate_audio(str(bad))
    assert is_valid is False
    assert msg is not None
    assert "Failed to load audio" in msg
