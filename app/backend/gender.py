"""Lightweight speaker-gender estimation from a speech WAV.

No heavy deps (stdlib `wave` + numpy): estimate the median fundamental
frequency (F0) via frame-wise autocorrelation, then threshold it. Adult male
voices sit roughly 85-180 Hz and female 165-255 Hz; ~165 Hz is the usual
split. This is a coarse "at least male/female" cue — the user can override it.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

# Median F0 at/above this (Hz) → female, below → male.
FEMALE_F0_HZ = 165.0
F0_MIN_HZ, F0_MAX_HZ = 70.0, 350.0


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


def estimate_gender(path: Path) -> str | None:
    """Return 'M', 'F', or None when the audio is too quiet/short to tell."""
    f0 = estimate_median_f0(path)
    if f0 is None:
        return None
    return "F" if f0 >= FEMALE_F0_HZ else "M"
