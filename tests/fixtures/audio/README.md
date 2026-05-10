# Audio test fixtures

All fixtures except `cough_clear.wav` are **synthesized at test session start**
by [`tests/fixtures/audio_factory.py`](../audio_factory.py). You don't need to
commit them — `conftest.py` regenerates them every run.

| Fixture | How it's produced | Used to test |
|---|---|---|
| `too_short.wav` | 1.5s sine — synthesized | Duration < 2s rejection |
| `cough_quiet.wav` | 3s very-low-amplitude sine — synthesized | RMS < 0.01 rejection |
| `white_noise.wav` | 3s broadband noise — synthesized | Spectral flatness > 0.5 rejection |
| `speech_like.wav` | 3s low-frequency tone (200Hz) — synthesized | "No cough freq" + low classifier confidence |
| `synthetic_cough.wav` | 4 noise bursts at 1500Hz — synthesized | Validator pass-through (passes all 4 checks) |
| `cough_clear.wav` | **Real recording — must be supplied** | End-to-end happy-path: classifier should return ≥ 0.25 |

## Providing `cough_clear.wav`

The ML happy-path test (`test_analyze_real_cough` in
`tests/integration/test_analysis_flow.py`) needs a real cough recording the
classifier can recognize. Synthesizing one that fools YAMNet + Random Forest
isn't reliable.

Drop a 3-5 second WAV file (16kHz mono preferred, but anything librosa can
load works) at `tests/fixtures/audio/cough_clear.wav`. Sources:

- Record yourself coughing into your mic for 4-5 seconds
- Use a CC-licensed sample from [FreeSound](https://freesound.org/search/?q=cough)
- Pull one from the [COUGHVID dataset](https://zenodo.org/records/4498364)

If the file is missing, the ML happy-path test is **skipped** (not failed)
with a clear message — see `pytest.importorskip` logic in `conftest.py`.
