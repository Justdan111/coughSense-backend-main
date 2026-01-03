import tensorflow as tf
import tensorflow_hub as hub
import librosa

YAMNET_URL = "https://tfhub.dev/google/yamnet/1"
yamnet = hub.load(YAMNET_URL)

def extract_yamnet_embedding(audio_path: str):
    y, sr = librosa.load(audio_path, sr=16000)
    waveform = tf.convert_to_tensor(y, dtype=tf.float32)

    _, embeddings, _ = yamnet(waveform)
    return tf.reduce_mean(embeddings, axis=0).numpy()
