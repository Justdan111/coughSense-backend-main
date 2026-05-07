import librosa
import numpy as np


def validate_audio(path: str) -> tuple[bool, str | None]:
    """
    Validate audio before sending to YAMNet.

    Checks:
        - Minimum duration (2 seconds)
        - Minimum loudness (RMS energy > 0.01)
        - Spectral flatness (rejects pure noise)
        - Cough-like energy in 500–4000 Hz range

    Returns:
        (is_valid, error_message)
    """
    try:
        y, sr = librosa.load(path, sr=16000)
    except Exception as e:
        return False, f"Failed to load audio: {str(e)}"

    # Duration check
    duration = librosa.get_duration(y=y, sr=sr)
    if duration < 2:
        return False, "Recording too short (minimum 2 seconds required)"

    # Loudness check
    rms = np.mean(librosa.feature.rms(y=y))
    if rms < 0.01:
        return False, "Audio too quiet"

    # Noise detection via spectral flatness
    flatness = np.mean(librosa.feature.spectral_flatness(y=y))
    if flatness > 0.5:
        return False, "Audio appears to be noise or silence"

    # Cough-like energy check (500–4000 Hz)
    spec = np.abs(librosa.stft(y))
    frequencies = librosa.fft_frequencies(sr=sr)
    speech_range = (frequencies >= 500) & (frequencies <= 4000)
    speech_energy = np.mean(spec[speech_range, :])
    total_energy = np.mean(spec)

    if total_energy > 0:
        energy_ratio = speech_energy / total_energy
        if energy_ratio < 0.2:
            return False, "Audio lacks distinct cough characteristics"

    return True, None