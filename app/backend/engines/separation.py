"""Audio source separation engines.

P1 exposes a small protocol first, then the concrete Demucs implementation.
Jobs and tests can swap the default engine without touching the queue layer.
"""
from __future__ import annotations

import subprocess
import time
import importlib.util
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


CheckCancel = Callable[[], None] | None


@dataclass(frozen=True)
class SeparationResult:
    vocals: Path
    accompaniment: Path


def _save_wav(tensor, samplerate: int, path: Path):
    """Write an audio tensor/array [channels, samples] to a 16-bit PCM WAV using
    only numpy + the stdlib — avoids torchaudio's save backend, which is often
    missing on Windows (`soundfile`/`sox` not installed → demucs save crashes)."""
    import numpy as np

    arr = tensor
    if hasattr(arr, "detach"):
        arr = arr.detach()
    if hasattr(arr, "cpu"):
        arr = arr.cpu()
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[None, :]
    data = np.clip(arr.T, -1.0, 1.0)               # [samples, channels]
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(int(samplerate))
        w.writeframes(pcm.tobytes())


class SeparationEngine(Protocol):
    name: str

    def separate_vocals(self, input_audio: Path, out_dir: Path,
                        check_cancel: CheckCancel = None) -> SeparationResult:
        """Create vocals.wav and accompaniment.wav under out_dir."""


def _run_cancelable(cmd: list[str], check_cancel: CheckCancel = None,
                    timeout: float = 7200):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    start = time.time()
    while True:
        try:
            _, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if check_cancel:
                try:
                    check_cancel()
                except BaseException:
                    proc.kill()
                    proc.communicate()
                    raise
            if time.time() - start > timeout:
                proc.kill()
                proc.communicate()
                raise RuntimeError("demucs timed out")
    if proc.returncode != 0:
        raise RuntimeError(f"demucs failed: {(err or '')[-800:]}")


class DemucsEngine:
    """Demucs htdemucs separation via its stable low-level functions.

    We deliberately avoid both the demucs CLI and `demucs.api`: the CLI saves
    stems with `torchaudio.save`, which needs a `soundfile`/`sox` backend that
    is absent on many Windows installs (torchaudio 2.x ships none), and
    `demucs.api` doesn't exist in demucs 4.0.1. Instead we load with demucs'
    ffmpeg-based `AudioFile`, run `apply_model`, and write the WAVs ourselves —
    no torchaudio backend required. Accompaniment = sum of the non-vocal stems
    (drums + bass + other). The model is cached across cuts.
    """

    name = "demucs"

    def __init__(self, model: str = "htdemucs"):
        self.model = model
        self._model_obj = None

    def _model(self):
        if self._model_obj is None:
            from demucs.pretrained import get_model
            m = get_model(self.model)
            m.eval()
            self._model_obj = m
        return self._model_obj

    def separate_vocals(self, input_audio: Path, out_dir: Path,
                        check_cancel: CheckCancel = None) -> SeparationResult:
        from demucs.apply import apply_model
        from demucs.audio import AudioFile

        out_dir.mkdir(parents=True, exist_ok=True)
        if check_cancel:
            check_cancel()
        model = self._model()
        wav = AudioFile(str(input_audio)).read(
            streams=0, samplerate=model.samplerate, channels=model.audio_channels)
        ref = wav.mean(0)
        wav_n = (wav - ref.mean()) / (ref.std() + 1e-8)   # demucs normalization
        if check_cancel:
            check_cancel()
        sources = apply_model(model, wav_n[None], device="cpu", split=True,
                              overlap=0.25, progress=False)[0]
        sources = sources * ref.std() + ref.mean()
        if check_cancel:
            check_cancel()

        names = list(model.sources)
        if "vocals" not in names:
            raise RuntimeError("demucs model has no vocals stem")
        vi = names.index("vocals")
        vocals_t = sources[vi]
        others = [sources[i] for i in range(len(names)) if i != vi]
        if not others:
            raise RuntimeError("demucs produced no accompaniment stems")
        accomp_t = others[0].clone()
        for o in others[1:]:
            accomp_t = accomp_t + o

        vocals = out_dir / "vocals.wav"
        accompaniment = out_dir / "accompaniment.wav"
        _save_wav(vocals_t, model.samplerate, vocals)
        _save_wav(accomp_t, model.samplerate, accompaniment)
        return SeparationResult(vocals=vocals, accompaniment=accompaniment)


def _audio_channels(path: Path) -> int:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a:0",
             "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return int((out.stdout or "0").strip() or 0)
    except Exception:
        return 0


class CenterCancelEngine:
    """No-Demucs fallback that *actually* removes vocals (not a passthrough).

    Lead vocals in stereo content are almost always panned dead-centre, so the
    L−R "side" signal cancels them — that becomes the accompaniment. The mono
    sum (L+R) keeps the centre and serves as a rough vocal estimate (good enough
    to gauge a speaker's pitch/gender). This is crude karaoke-style removal, so
    `degraded` is True and callers should recommend Demucs for clean stems.

    A MONO source has no spatial information to exploit, so we refuse rather
    than silently leave the original dialogue under the dub — the exact bug this
    replaces.
    """

    name = "center-cancel"
    degraded = True

    def separate_vocals(self, input_audio: Path, out_dir: Path,
                        check_cancel: CheckCancel = None) -> SeparationResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        vocals = out_dir / "vocals.wav"
        accompaniment = out_dir / "accompaniment.wav"
        if _audio_channels(input_audio) < 2:
            raise RuntimeError(
                "this source is mono, so vocals can't be removed without Demucs. "
                "Install it with:  pip install demucs  "
                "(the no-Demucs fallback only works on stereo audio by cancelling "
                "centre-panned vocals).")
        # accompaniment: cancel the centre (vocals) via the stereo side signal
        _run_cancelable([
            "ffmpeg", "-y", "-i", str(input_audio),
            "-af", "pan=stereo|c0=c0-c1|c1=c1-c0",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(accompaniment),
        ], check_cancel)
        # rough vocal estimate: the centred mono sum (for pitch/gender only)
        _run_cancelable([
            "ffmpeg", "-y", "-i", str(input_audio),
            "-af", "pan=mono|c0=0.5*c0+0.5*c1",
            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(vocals),
        ], check_cancel)
        return SeparationResult(vocals=vocals, accompaniment=accompaniment)


_default_engine: SeparationEngine | None = None


def get_separation_engine() -> SeparationEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = (DemucsEngine()
                           if importlib.util.find_spec("demucs") is not None
                           else CenterCancelEngine())
    return _default_engine


def engine_is_degraded() -> bool:
    return bool(getattr(get_separation_engine(), "degraded", False))


def set_separation_engine(engine: SeparationEngine | None):
    """Override for tests or alternate local engines."""
    global _default_engine
    _default_engine = engine
