"""Audio source separation engines.

P1 exposes a small protocol first, then the concrete Demucs implementation.
Jobs and tests can swap the default engine without touching the queue layer.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


CheckCancel = Callable[[], None] | None


@dataclass(frozen=True)
class SeparationResult:
    vocals: Path
    accompaniment: Path


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
    """Demucs htdemucs two-stem separation.

    The command writes Demucs' native tree into a temporary folder, then copies
    the two expected stems into stable cache names used by later phases.
    """

    name = "demucs"

    def __init__(self, model: str = "htdemucs"):
        self.model = model

    def separate_vocals(self, input_audio: Path, out_dir: Path,
                        check_cancel: CheckCancel = None) -> SeparationResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        work = out_dir / "_demucs"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "-m", "demucs",
            "-n", self.model,
            "--two-stems", "vocals",
            "-o", str(work),
            str(input_audio),
        ]
        _run_cancelable(cmd, check_cancel)

        native_dir = work / self.model / input_audio.stem
        vocals_src = native_dir / "vocals.wav"
        accomp_src = native_dir / "no_vocals.wav"
        if not vocals_src.exists() or not accomp_src.exists():
            raise RuntimeError("demucs did not produce vocals/no_vocals stems")

        vocals = out_dir / "vocals.wav"
        accompaniment = out_dir / "accompaniment.wav"
        shutil.copy2(vocals_src, vocals)
        shutil.copy2(accomp_src, accompaniment)
        shutil.rmtree(work, ignore_errors=True)
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
