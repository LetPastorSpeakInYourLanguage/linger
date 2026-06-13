"""Speaker-gender estimation from a speech WAV.

Two methods, best-to-worst:

1. **Resemblyzer speaker embedding** (preferred, optional dep): embed the clip
   with a `VoiceEncoder`, then take the gender of the nearest labelled
   reference — exactly the approach in the user's notebooks, which compared an
   utterance embedding (cosine similarity) to a labelled VCTK set. We don't
   ship VCTK, so we build male/female reference centroids once from known-gender
   Edge-TTS voices and cache them. Needs `pip install resemblyzer` + one online
   build.

2. **Pitch (median F0)** fallback (no heavy deps, stdlib `wave` + numpy):
   autocorrelation F0, thresholded at ~165 Hz. A coarse "at least male/female"
   cue.

Either way the user can override the result per segment or per dub.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

# Median F0 at/above this (Hz) → female, below → male.
FEMALE_F0_HZ = 165.0
F0_MIN_HZ, F0_MAX_HZ = 70.0, 350.0

# Known-gender Edge-TTS voices used to build reference centroids in embedding
# space (a few per gender, multiple accents for robustness).
REFERENCE_VOICES = [
    ("en-US-JennyNeural", "F"), ("en-GB-SoniaNeural", "F"), ("en-AU-NatashaNeural", "F"),
    ("en-US-GuyNeural", "M"), ("en-GB-RyanNeural", "M"), ("en-AU-WilliamNeural", "M"),
]
_REF_PHRASE = ("The quick brown fox jumps over the lazy dog while the sun sets "
               "slowly behind the distant green hills.")

_encoder = None
_refs = None  # (female_centroid, male_centroid) or False once known-unavailable


def _read_wav_mono(path: Path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        sampwidth = w.getsampwidth()
        channels = w.getnchannels()
        raw = w.readframes(w.getnframes())
    if sampwidth != 2 or not raw:
        return None, sr
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sr


def _frame_f0(frame: np.ndarray, sr: int) -> float | None:
    """Autocorrelation pitch for one voiced frame, or None if unvoiced."""
    frame = frame - frame.mean()
    energy = np.sqrt(np.mean(frame ** 2))
    if energy < 80:  # near-silence (int16 scale): unvoiced
        return None
    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
    min_lag = int(sr / F0_MAX_HZ)
    max_lag = min(int(sr / F0_MIN_HZ), len(corr) - 1)
    if max_lag <= min_lag:
        return None
    window = corr[min_lag:max_lag]
    peak = int(np.argmax(window)) + min_lag
    if corr[0] <= 0 or corr[peak] / corr[0] < 0.3:  # weakly periodic: skip
        return None
    return sr / peak


def estimate_median_f0(path: Path) -> float | None:
    data, sr = _read_wav_mono(path)
    if data is None or sr <= 0 or len(data) < int(sr * 0.2):
        return None
    frame_len = int(sr * 0.04)   # 40 ms frames, 20 ms hop
    hop = int(sr * 0.02)
    if frame_len <= 0:
        return None
    f0s = [f for start in range(0, len(data) - frame_len, hop)
           if (f := _frame_f0(data[start:start + frame_len], sr)) is not None]
    if len(f0s) < 3:
        return None
    return float(np.median(f0s))


def estimate_gender_pitch(path: Path) -> str | None:
    """Coarse gender from median F0. 'M', 'F', or None when too quiet/short."""
    f0 = estimate_median_f0(path)
    if f0 is None:
        return None
    return "F" if f0 >= FEMALE_F0_HZ else "M"


# --------------------------------------------------- resemblyzer embeddings

def _cos(a, b) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)


def _get_encoder():
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder(verbose=False)
    return _encoder


def _refs_path() -> Path:
    from . import media_ops
    return media_ops.MEDIA_ROOT / ".gender_refs.npz"


def _build_reference_centroids() -> tuple[np.ndarray, np.ndarray]:
    """Synthesize the known-gender reference voices once, embed them, and store
    the per-gender mean embedding — the labelled set the notebooks compared to."""
    import tempfile
    from resemblyzer import preprocess_wav
    from .engines.tts import EdgeTTSEngine

    enc = _get_encoder()
    engine = EdgeTTSEngine()
    by_gender: dict[str, list[np.ndarray]] = {"F": [], "M": []}
    with tempfile.TemporaryDirectory() as td:
        for voice, g in REFERENCE_VOICES:
            try:
                out = Path(td) / f"{voice}.mp3"
                engine.synthesize(_REF_PHRASE, voice, out)
                by_gender[g].append(enc.embed_utterance(preprocess_wav(out)))
            except Exception:
                continue
    if not by_gender["F"] or not by_gender["M"]:
        raise RuntimeError("could not build gender reference centroids")
    female = np.mean(by_gender["F"], axis=0)
    male = np.mean(by_gender["M"], axis=0)
    np.savez(_refs_path(), female=female, male=male)
    return female, male


def _get_reference_centroids():
    global _refs
    if _refs is not None:
        return _refs or None
    path = _refs_path()
    try:
        if path.exists():
            data = np.load(path)
            _refs = (data["female"], data["male"])
        else:
            _refs = _build_reference_centroids()
    except Exception:
        _refs = False  # remember failure; don't retry every call
        return None
    return _refs


def estimate_gender_embedding(path: Path) -> str | None:
    """Nearest-gender by resemblyzer speaker embedding, or None if unavailable."""
    try:
        from resemblyzer import preprocess_wav
        refs = _get_reference_centroids()
        if not refs:
            return None
        female, male = refs
        emb = _get_encoder().embed_utterance(preprocess_wav(Path(path)))
        return "F" if _cos(emb, female) >= _cos(emb, male) else "M"
    except Exception:
        return None


def estimate_gender(path: Path) -> str | None:
    """Best available speaker-gender estimate: resemblyzer embedding when
    installed/buildable, else pitch. 'M', 'F', or None."""
    return estimate_gender_embedding(path) or estimate_gender_pitch(path)
