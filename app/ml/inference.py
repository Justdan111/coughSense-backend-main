import joblib
import numpy as np
from app.ml.yamnet_model import extract_yamnet_embedding

classifier = joblib.load("app/ml/yamnet_random_forest.joblib")
yamnet_mean = np.load("app/ml/yamnet_mean.npy")

def predict_from_audio(audio_path: str):
    emb = extract_yamnet_embedding(audio_path)
    emb = emb - yamnet_mean

    prob = classifier.predict_proba([emb])[0][1]

    if prob < 0.4:
        risk = "Low"
    elif prob < 0.7:
        risk = "Moderate"
    else:
        risk = "High"

    return risk, round(float(prob) * 100, 2)
