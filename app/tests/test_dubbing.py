"""Dubbing fixes: real vocal removal (no silent passthrough) and gender voices."""
import subprocess
import wave

import numpy as np

from backend import gender
from backend.engines.separation import CenterCancelEngine


def _stereo_voiceish_wav(path, sr=22050, dur=1.5, left_hz=180.0):
    """A stereo clip with a centred 'voice' tone (same in L+R) plus different
    side content, so centre-cancellation has something real to remove."""
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    centre = 0.5 * np.sin(2 * np.pi * left_hz * t)        # 'vocal', centred
    side_l = 0.3 * np.sin(2 * np.pi * 320 * t)            # 'music' L
    side_r = 0.3 * np.sin(2 * np.pi * 90 * t)             # 'music' R
    left = np.clip(centre + side_l, -1, 1)
    right = np.clip(centre + side_r, -1, 1)
    stereo = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def _rms_of_centre(path):
    """RMS of the (L+R)/2 centre signal — where vocals live."""
    with wave.open(str(path), "rb") as w:
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    if ch == 2:
        data = data.reshape(-1, 2)
        centre = data.mean(axis=1)
    else:
        centre = data
    return float(np.sqrt(np.mean(centre ** 2)))


def test_center_cancel_actually_removes_centre_vocals(tmp_path):
    src = tmp_path / "mix.wav"
    _stereo_voiceish_wav(src)
    out = tmp_path / "stems"
    result = CenterCancelEngine().separate_vocals(src, out)
    assert result.accompaniment.exists() and result.vocals.exists()
    # the centred 'vocal' energy must drop sharply in the accompaniment —
    # the whole point: it is NOT a passthrough of the original mix
    assert _rms_of_centre(result.accompaniment) < 0.3 * _rms_of_centre(src)


def test_center_cancel_refuses_mono(tmp_path):
    mono = tmp_path / "mono.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200",
                    "-t", "1", "-ac", "1", str(mono)], capture_output=True, check=True)
    out = tmp_path / "stems"
    try:
        CenterCancelEngine().separate_vocals(mono, out)
        assert False, "mono should be refused, not silently passed through"
    except RuntimeError as e:
        assert "demucs" in str(e).lower()


def test_gender_estimate_low_vs_high_pitch(tmp_path):
    male = tmp_path / "male.wav"
    female = tmp_path / "female.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=110",
                    "-t", "1.5", "-ar", "22050", "-ac", "1", str(male)],
                   capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=230",
                    "-t", "1.5", "-ar", "22050", "-ac", "1", str(female)],
                   capture_output=True, check=True)
    assert gender.estimate_gender(male) == "M"
    assert gender.estimate_gender(female) == "F"
