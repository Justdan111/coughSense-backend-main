from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.deps.auth import get_current_user
from app.ml.inference import predict_from_audio
from app.ml.validator import validate_audio
from app.utils.audio import save_temp_audio

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

def risk_message(severity: str):
    if severity == "High":
        return {
            "risk_level": "high",
            "summary": "Your cough pattern shows a high respiratory risk.",
            "recommendation": "Seek medical attention as soon as possible.",
            "actions": [
                "Visit a healthcare facility",
                "Avoid close contact with others",
                "Monitor breathing difficulty or chest pain"
            ]
        }

    if severity == "Moderate":
        return {
            "risk_level": "medium",
            "summary": "Your cough shows moderate respiratory risk.",
            "recommendation": "Consider consulting a healthcare professional.",
            "actions": [
                "Monitor symptoms",
                "Rest and stay hydrated",
                "Seek care if symptoms worsen"
            ]
        }

    return {
        "risk_level": "low",
        "summary": "Your cough shows low respiratory risk.",
        "recommendation": "No urgent medical action required.",
        "actions": [
            "Maintain good hydration",
            "Monitor your health",
            "Practice good hygiene"
        ]
    }

@router.post("/analysis/analyze")
async def analyze_cough(
    audio: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    # Validate file type
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}"
        )
    
    path = save_temp_audio(audio)
    
    # Validate audio quality before prediction
    is_valid, error_msg = validate_audio(path)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audio sample. {error_msg}. Please record 3–5 distinct coughs in a quiet environment."
        )
    
    severity, confidence, probs = predict_from_audio(path)
    
    # Reject predictions with low confidence
    if confidence < 55:
        raise HTTPException(
            status_code=400,
            detail="Unable to confidently analyze sample. Please record clearer cough sounds."
        )

    guidance = risk_message(severity)

    return {
         "user_id": user_id,
        "severity": severity,
        "confidence": confidence,
        **guidance,
        "disclaimer": (
            "This system is for triage purposes only and does not provide "
            "a medical diagnosis. Always consult a qualified healthcare professional."
        )
    }