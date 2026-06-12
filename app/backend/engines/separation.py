"""Audio source separation engines.

P1 exposes a small protocol first, then the concrete Demucs implementation.
Jobs and tests can swap the default engine without touching the queue layer.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
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


_default_engine: SeparationEngine | None = None


def get_separation_engine() -> SeparationEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = DemucsEngine()
    return _default_engine


def set_separation_engine(engine: SeparationEngine | None):
    """Override for tests or alternate local engines."""
    global _default_engine
    _default_engine = engine
