"""
Integration tests for /api/analysis/analyze and /api/analysis/assess.

Hits real Supabase for auth + (optionally) storage/db; loads the real
YAMNet + Random Forest model. The ML happy-path test is auto-skipped
when `tests/fixtures/audio/cough_clear.wav` is not present.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.integration, pytest.mark.ml]

REAL_COUGH = Path(__file__).parent.parent / "fixtures" / "audio" / "cough_clear.wav"


# ─────────────────────────────────────────────────────────────────────
# /analyze — input validation
# ─────────────────────────────────────────────────────────────────────

def test_analyze_requires_auth(client: TestClient, audio_fixture):
    r = client.post(
        "/api/analysis/analyze",
        files={"audio": audio_fixture("synthetic_cough.wav")},
    )
    assert r.status_code in (401, 403)


def test_analyze_rejects_unsupported_mime(client: TestClient, auth_headers):
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert "invalid file type" in r.json()["detail"].lower()


def test_analyze_rejects_too_short(client: TestClient, auth_headers, audio_fixture):
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": audio_fixture("too_short.wav")},
    )
    assert r.status_code == 400
    assert "2 seconds" in r.json()["detail"]


def test_analyze_rejects_quiet(client: TestClient, auth_headers, audio_fixture):
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": audio_fixture("cough_quiet.wav")},
    )
    assert r.status_code == 400
    assert "quiet" in r.json()["detail"].lower()


def test_analyze_rejects_white_noise(client: TestClient, auth_headers, audio_fixture):
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": audio_fixture("white_noise.wav")},
    )
    assert r.status_code == 400


def test_analyze_low_freq_rejected(client: TestClient, auth_headers, audio_fixture):
    """Low-freq tone may be rejected at the validator OR at the < 0.25 confidence gate."""
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": audio_fixture("speech_like.wav")},
    )
    assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────
# /analyze — ML happy path (requires real cough audio)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not REAL_COUGH.exists(),
    reason="cough_clear.wav not provided — see tests/fixtures/audio/README.md",
)
def test_analyze_real_cough(client: TestClient, auth_headers, test_user):
    r = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": ("cough_clear.wav", REAL_COUGH.read_bytes(), "audio/wav")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == test_user["id"]
    assert 0.25 <= body["cough_confidence"] <= 1.0
    assert body["cough_confidence_pct"] == round(body["cough_confidence"] * 100, 2)
    assert "disclaimer" in body


# ─────────────────────────────────────────────────────────────────────
# /assess — symptom + confidence triage (no audio, no model load needed)
# ─────────────────────────────────────────────────────────────────────

def test_assess_low_risk(client: TestClient, auth_headers, test_user):
    r = client.post(
        "/api/analysis/assess",
        headers=auth_headers,
        json={
            "cough_confidence": 0.3,
            "fever": False,
            "blood": False,
            "chest_pain": False,
            "difficulty_breathing": False,
            "save_for_training": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == test_user["id"]
    assert body["result"] == "less_risky"
    assert body["score"] == 1
    assert "recommendation" in body
    assert isinstance(body["actions"], list)


def test_assess_high_risk_blood(client: TestClient, auth_headers):
    r = client.post(
        "/api/analysis/assess",
        headers=auth_headers,
        json={
            "cough_confidence": 0.5,
            "fever": False,
            "blood": True,
            "chest_pain": False,
            "difficulty_breathing": False,
            "save_for_training": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"] == "risky"
    assert body["score"] >= 4
    joined = " ".join(body["actions"]).lower()
    assert "blood" in joined


def test_assess_requires_auth(client: TestClient):
    r = client.post(
        "/api/analysis/assess",
        json={"cough_confidence": 0.5},
    )
    assert r.status_code in (401, 403)


def test_assess_rejects_missing_confidence(client: TestClient, auth_headers):
    r = client.post(
        "/api/analysis/assess",
        headers=auth_headers,
        json={"fever": True},
    )
    assert r.status_code == 422


@pytest.mark.skipif(
    not REAL_COUGH.exists(),
    reason="full pipeline requires cough_clear.wav",
)
def test_full_pipeline_analyze_then_assess(client: TestClient, auth_headers):
    a = client.post(
        "/api/analysis/analyze",
        headers=auth_headers,
        files={"audio": ("cough_clear.wav", REAL_COUGH.read_bytes(), "audio/wav")},
    )
    assert a.status_code == 200
    confidence = a.json()["cough_confidence"]

    b = client.post(
        "/api/analysis/assess",
        headers=auth_headers,
        json={
            "cough_confidence": confidence,
            "fever": True,
            "blood": False,
            "chest_pain": True,
            "difficulty_breathing": False,
        },
    )
    assert b.status_code == 200
    assert b.json()["result"] in {"risky", "less_risky"}
