import joblib
import numpy as np
from app.ml.yamnet_model import extract_yamnet_embedding

classifier = joblib.load("app/models/yamnet_random_forest.joblib")
yamnet_mean = np.load("app/models/yamnet_mean.npy")


def predict_from_audio(audio_path: str) -> float:
    """
    Run YAMNet + classifier on audio file.
    Returns cough confidence score between 0.0 and 1.0.
    """
    emb = extract_yamnet_embedding(audio_path)
    emb = emb - yamnet_mean

    probs = classifier.predict_proba([emb])[0]
    classes = list(classifier.classes_)

    # Try to locate a class that indicates "cough" (robust to label names)
    cough_idx = None
    for i, c in enumerate(classes):
        try:
            if isinstance(c, str) and "cough" in c.lower():
                cough_idx = i
                break
        except Exception:
            continue

    # Handle numeric labels where 1 may represent cough
    if cough_idx is None:
        try:
            if 1 in classes:
                cough_idx = classes.index(1)
        except Exception:
            pass

    # Fallback for binary models: assume positive class is index 1
    if cough_idx is None and len(probs) == 2:
        cough_idx = 1

    if cough_idx is None:
        raise ValueError(f"Unable to locate 'cough' class in classifier.classes_: {classes}")

    cough_prob = float(probs[cough_idx])
    not_cough_prob = None
    if len(probs) == 2:
        not_cough_prob = float(probs[1 - cough_idx])

    # Log classes and probabilities for debugging
    debug = {"classes": classes, "probs": [round(float(p) * 100, 2) for p in probs]}
    if not_cough_prob is not None:
        print({"not_cough": round(not_cough_prob * 100, 2), "cough": round(cough_prob * 100, 2), "classes": classes})
    else:
        print(debug)

    return round(cough_prob, 4)


def calculate_risk(cough_confidence: float, symptoms: dict) -> dict:
    """
    Combine audio cough confidence with symptom answers
    to produce a triage risk result.

    Scoring:
        Audio:
            >= 0.7  → 3 pts
            >= 0.4  → 2 pts
            < 0.4   → 1 pt

        Symptoms:
            blood                → 4 pts  (strongest red flag)
            chest_pain           → 2 pts
            difficulty_breathing → 2 pts
            fever                → 1 pt

        Threshold:
            score >= 4 → risky
            score <  4 → less_risky
    """
    score = 0

    # Audio contribution
    if cough_confidence >= 0.7:
        score += 3
    elif cough_confidence >= 0.4:
        score += 2
    else:
        score += 1

    # Symptom contributions
    if symptoms.get("blood"):
        score += 4
    if symptoms.get("chest_pain"):
        score += 2
    if symptoms.get("difficulty_breathing"):
        score += 2
    if symptoms.get("fever"):
        score += 1

    result = "risky" if score >= 4 else "less_risky"

    return {
        "result": result,
        "cough_confidence": round(cough_confidence * 100, 2),
        "score": score,
    }