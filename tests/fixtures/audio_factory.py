"""
Synthesize the audio fixtures the test suite needs at import time.

The validator at app/ml/validator.py rejects audio on four criteria:
    - duration < 2s
    - RMS energy < 0.01
    - spectral flatness > 0.5  (treated as noise)
    - 500-4000Hz energy ratio < 0.2

We construct a fixture for each rejection branch plus one that passes
validation but produces low cough confidence (sine-only "speech-like").

Real cough audio cannot be plausibly synthesized; the cough_clear.wav
fixture must be supplied by the user (see tests/fixtures/audio/README.md).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16000
FIXTURE_DIR = Path(__file__).parent / "audio"


def _write(name: str, samples: np.ndarray) -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / name
    sf.write(path, samples.astype(np.float32), SAMPLE_RATE, subtype="PCM_16")
    return path


def too_short() -> Path:
    """1.5 seconds — fails the duration check (min 2s)."""
    duration = 1.5
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    samples = 0.3 * np.sin(2 * np.pi * 1000 * t)
    return _write("too_short.wav", samples)


def cough_quiet() -> Path:
    """3 seconds at very low amplitude — fails the RMS check."""
    duration = 3.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    samples = 0.001 * np.sin(2 * np.pi * 1500 * t)
    return _write("cough_quiet.wav", samples)


def white_noise() -> Path:
    """3 seconds of broadband noise — high spectral flatness, fails noise check."""
    rng = np.random.default_rng(seed=42)
    samples = 0.3 * rng.standard_normal(int(SAMPLE_RATE * 3.0))
    return _write("white_noise.wav", samples)


def speech_like() -> Path:
    """
    3 seconds of low-frequency tone (200Hz fundamental).
    Passes loudness + flatness checks but fails the 500-4000Hz energy-ratio
    check, OR passes validation but the classifier returns very low cough
    confidence — covering the < 0.25 rejection branch in /analyze.
    """
    duration = 3.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    samples = 0.3 * np.sin(2 * np.pi * 200 * t) + 0.1 * np.sin(2 * np.pi * 350 * t)
    return _write("speech_like.wav", samples)


def synthetic_cough() -> Path:
    """
    Best-effort synthetic cough: continuous tonal carrier in the cough band
    (1500 + 2200 Hz) modulated by a slow 4-burst envelope over 3 seconds,
    with a small noise component for realism.

    Designed to pass all 4 validator checks:
      - 3.0s duration (>= 2.0s)
      - RMS ~0.25 (>= 0.01)
      - spectral flatness low (~0.05) because tonal energy dominates
      - 500-4000 Hz energy ratio high (carrier is centered there)

    It won't fool YAMNet — the ML happy-path test needs a real cough.
    """
    duration = 3.0
    n = int(SAMPLE_RATE * duration)
    rng = np.random.default_rng(seed=1)
    t = np.arange(n) / SAMPLE_RATE

    # Continuous tonal carrier in the cough frequency band
    carrier = (
        0.6 * np.sin(2 * np.pi * 1500 * t)
        + 0.3 * np.sin(2 * np.pi * 2200 * t)
        + 0.1 * np.sin(2 * np.pi * 900 * t)
    )

    # Small amount of noise for realism — kept low so spectral flatness stays low
    noise = 0.05 * rng.standard_normal(n)

    # Burst envelope: 4 sharp peaks over 3 seconds with a 0.1 floor so the
    # signal never goes silent (preserves overall loudness for RMS check)
    envelope = np.full(n, 0.1, dtype=np.float32)
    burst_centers = [0.3, 1.0, 1.7, 2.4]
    burst_width = 0.15  # seconds
    for c in burst_centers:
        peak = int(c * SAMPLE_RATE)
        width = int(burst_width * SAMPLE_RATE)
        start = max(0, peak - width)
        end = min(n, peak + width)
        # Triangular peak
        idx = np.arange(start, end)
        envelope[idx] = np.maximum(envelope[idx], 1.0 - np.abs(idx - peak) / width)

    out = (carrier + noise) * envelope * 0.5
    return _write("synthetic_cough.wav", out)


def ensure_all() -> dict[str, Path]:
    """Generate every synthesized fixture and return name → path mapping."""
    return {
        "too_short": too_short(),
        "cough_quiet": cough_quiet(),
        "white_noise": white_noise(),
        "speech_like": speech_like(),
        "synthetic_cough": synthetic_cough(),
    }


if __name__ == "__main__":
    paths = ensure_all()
    for name, path in paths.items():
        print(f"  {name:20s} → {path}")
