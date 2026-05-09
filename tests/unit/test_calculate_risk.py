"""Unit tests for app.ml.inference.calculate_risk — pure scoring math."""
from __future__ import annotations

import pytest

from app.ml.inference import calculate_risk


def _no_symptoms() -> dict:
    return {"fever": False, "blood": False, "chest_pain": False, "difficulty_breathing": False}


@pytest.mark.parametrize(
    "confidence, symptoms, expected_score, expected_result",
    [
        # --- Audio bands only (no symptoms) ---
        # confidence >= 0.7 → 3 pts; threshold for risky is >= 4, so 3 → less_risky
        (0.95, _no_symptoms(), 3, "less_risky"),
        (0.70, _no_symptoms(), 3, "less_risky"),
        # 0.4 <= confidence < 0.7 → 2 pts
        (0.55, _no_symptoms(), 2, "less_risky"),
        (0.40, _no_symptoms(), 2, "less_risky"),
        # confidence < 0.4 → 1 pt
        (0.39, _no_symptoms(), 1, "less_risky"),
        (0.00, _no_symptoms(), 1, "less_risky"),
        # --- Single-symptom contributions ---
        # blood alone: 4pts + 1pt audio = 5 → risky
        (0.10, {**_no_symptoms(), "blood": True}, 5, "risky"),
        # chest_pain: 2 + 1 = 3 → less_risky (just under threshold)
        (0.10, {**_no_symptoms(), "chest_pain": True}, 3, "less_risky"),
        # difficulty_breathing: 2 + 1 = 3 → less_risky
        (0.10, {**_no_symptoms(), "difficulty_breathing": True}, 3, "less_risky"),
        # fever alone: 1 + 1 = 2 → less_risky
        (0.10, {**_no_symptoms(), "fever": True}, 2, "less_risky"),
        # --- Threshold boundary at score==4 ---
        # chest_pain (2) + difficulty_breathing (2) + audio (1) = 5 → risky
        (0.20, {**_no_symptoms(), "chest_pain": True, "difficulty_breathing": True}, 5, "risky"),
        # fever (1) + chest_pain (2) + audio (2) = 5 → risky
        (0.50, {**_no_symptoms(), "fever": True, "chest_pain": True}, 5, "risky"),
        # All symptoms + high audio: 3 + 4 + 2 + 2 + 1 = 12 → risky
        (0.95, {"fever": True, "blood": True, "chest_pain": True, "difficulty_breathing": True}, 12, "risky"),
    ],
)
def test_calculate_risk_score_and_result(confidence, symptoms, expected_score, expected_result):
    out = calculate_risk(confidence, symptoms)
    assert out["score"] == expected_score
    assert out["result"] == expected_result


def test_calculate_risk_returns_confidence_pct():
    out = calculate_risk(0.42, _no_symptoms())
    assert out["cough_confidence"] == 42.0


def test_calculate_risk_threshold_is_inclusive_at_4():
    # blood (4pt) alone with 0 audio? Audio still adds 1 -> 5. We need to test
    # the exact "score == 4" boundary, which requires fever(1) + chest_pain(2)
    # + audio(1, low band) = 4 exactly.
    out = calculate_risk(0.30, {**_no_symptoms(), "fever": True, "chest_pain": True})
    assert out["score"] == 4
    assert out["result"] == "risky"  # threshold is >= 4


def test_calculate_risk_handles_missing_symptom_keys():
    # `symptoms.get("blood")` returns None when key missing → falsy
    out = calculate_risk(0.5, {})
    assert out["score"] == 2  # only the audio (0.4 <= 0.5 < 0.7) contributes
    assert out["result"] == "less_risky"
