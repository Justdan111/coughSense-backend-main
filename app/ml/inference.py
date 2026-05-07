import joblib
import numpy as np
from app.ml.yamnet_model import extract_yamnet_embedding

classifier = joblib.load("app/ml/yamnet_random_forest.joblib")
yamnet_mean = np.load("app/ml/yamnet_mean.npy")

def predict_from_audio(audio_path: str):
    emb = extract_yamnet_embedding(audio_path)
    emb = emb - yamnet_mean

    probs = classifier.predict_proba([emb])[0]
    
    # Get cough probability (class 1)
    cough_prob = probs[1]
    
    # Log probabilities for debugging
    print({
        "not_cough": round(float(probs[0]) * 100, 2),
        "cough": round(float(cough_prob) * 100, 2)
    })
    
    # Get confidence (max probability)
    confidence = max(probs)
    
    # Determine risk level based on cough probability
    if cough_prob < 0.4:
        risk = "Low"
    elif cough_prob < 0.7:
        risk = "Moderate"
    else:
        risk = "High"

    return risk, round(float(confidence) * 100, 2), probs
