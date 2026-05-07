import os
import uuid
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Header
from pydantic import BaseModel

from app.deps.auth import get_current_user
from app.ml.inference import predict_from_audio, calculate_risk
from app.ml.validator import validate_audio
from app.core.supabase import supabase

router = APIRouter()

ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
    "audio/x-wav",
    "audio/x-m4a",
}

DISCLAIMER = (
    "This result is for triage purposes only and does not constitute a medical "
    "diagnosis. Always consult a qualified healthcare professional for any "
    "health concerns."
)


# ─────────────────────────────────────────────
# Response helpers
# ─────────────────────────────────────────────

def triage_guidance(result: str) -> dict:
    if result == "risky":
        return {
            "summary": "Your cough pattern and symptoms suggest a higher respiratory risk.",
            "recommendation": "Please seek medical attention soon.",
            "actions": [
                "Visit a clinic or hospital as soon as possible",
                "Avoid close contact with others until assessed",
                "Monitor for worsening chest pain or difficulty breathing",
                "Do not ignore coughing up blood — seek urgent care immediately",
            ],
        }

    return {
        "summary": "Your cough pattern and symptoms suggest a lower respiratory risk.",
        "recommendation": "No urgent medical action required, but stay alert.",
        "actions": [
            "Rest and stay well hydrated",
            "Monitor your symptoms over the next 48 hours",
            "Seek medical advice if symptoms persist beyond one week",
            "Practice good hygiene to avoid spreading illness",
        ],
    }


# ─────────────────────────────────────────────
# Supabase storage helper
# ─────────────────────────────────────────────

def save_to_supabase(
    user_id: str,
    temp_path: str,
    original_filename: str,
    cough_confidence: float,
    symptoms: dict,
    result: str,
    score: int,
):
    """
    Upload audio to Supabase Storage and insert metadata row.
    Only called when user has consented in settings.
    """
    unique_name = f"{uuid.uuid4()}_{Path(original_filename).name}"

    try:
        with open(temp_path, "rb") as f:
            supabase.storage.from_("cough-data").upload(
                unique_name,
                f,
                {"content-type": "audio/wav"},
            )
    except Exception as e:
        # Storage failure should not break the response
        print(f"[Supabase Storage] Upload failed: {e}")
        return

    try:
        supabase.table("cough_samples").insert({
            "user_id": user_id,
            "filename": unique_name,
            "cough_confidence": round(cough_confidence * 100, 2),
            "fever": symptoms.get("fever", False),
            "blood": symptoms.get("blood", False),
            "chest_pain": symptoms.get("chest_pain", False),
            "difficulty_breathing": symptoms.get("difficulty_breathing", False),
            "result": result,
            "score": score,
            "consent": True,
        }).execute()
    except Exception as e:
        print(f"[Supabase DB] Insert failed: {e}")


# ─────────────────────────────────────────────
# Request model for /assess
# ─────────────────────────────────────────────

class AssessRequest(BaseModel):
    cough_confidence: float          # raw value from /analyze (0.0–1.0)
    fever: bool = False
    blood: bool = False
    chest_pain: bool = False
    difficulty_breathing: bool = False
    save_for_training: bool = False  # mirrors user's consent setting


# ─────────────────────────────────────────────
# STEP 1 — Audio analysis
# ─────────────────────────────────────────────

@router.post("/analysis/analyze")
async def analyze_cough(
    audio: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Accepts a cough audio file.
    Returns cough_confidence score (0.0–1.0).
    Frontend uses this to show the symptom form.
    """
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid file type. "
                f"Allowed: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}"
            ),
        )

    # Save to temp file
    suffix = Path(audio.filename or "audio").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(audio.file, tmp)
        temp_path = tmp.name

    try:
        # Validate audio quality
        is_valid, error_msg = validate_audio(temp_path)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid audio sample. {error_msg}. "
                    "Please record 3–5 distinct coughs in a quiet environment."
                ),
            )

        cough_confidence = predict_from_audio(temp_path)

        # Reject very low confidence — likely not a cough at all
        if cough_confidence < 0.25:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No cough detected in this recording. "
                    "Please record clearer cough sounds."
                ),
            )

    finally:
        os.unlink(temp_path)

    return {
        "user_id": user_id,
        "cough_confidence": cough_confidence,
        "cough_confidence_pct": round(cough_confidence * 100, 2),
        "disclaimer": DISCLAIMER,
    }


# ─────────────────────────────────────────────
# STEP 2 — Symptom assessment + risk result
# ─────────────────────────────────────────────

@router.post("/analysis/assess")
async def assess_risk(
    data: AssessRequest,
    audio: UploadFile = File(None),   # optional — only needed if saving
    user_id: str = Depends(get_current_user),
):
    """
    Combines cough confidence with symptom answers.
    Returns triage result: risky or less_risky.
    Optionally saves audio + metadata to Supabase if user consented.
    """
    symptoms = {
        "fever": data.fever,
        "blood": data.blood,
        "chest_pain": data.chest_pain,
        "difficulty_breathing": data.difficulty_breathing,
    }

    risk = calculate_risk(
        cough_confidence=data.cough_confidence,
        symptoms=symptoms,
    )

    result = risk["result"]
    score = risk["score"]
    guidance = triage_guidance(result)

    # Save to Supabase if user consented and audio file provided
    if data.save_for_training and audio is not None:
        suffix = Path(audio.filename or "audio").suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(audio.file, tmp)
            temp_path = tmp.name
        try:
            save_to_supabase(
                user_id=user_id,
                temp_path=temp_path,
                original_filename=audio.filename or "recording.wav",
                cough_confidence=data.cough_confidence,
                symptoms=symptoms,
                result=result,
                score=score,
            )
        finally:
            os.unlink(temp_path)

    return {
        "user_id": user_id,
        "result": result,
        "cough_confidence_pct": risk["cough_confidence_pct"] if "cough_confidence_pct" in risk else round(data.cough_confidence * 100, 2),
        "score": score,
        **guidance,
        "disclaimer": DISCLAIMER,
    }