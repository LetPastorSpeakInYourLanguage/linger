"""Narration voices: kokoro (neural, ~350 MB downloaded once into <workspace>/.models) | system (pyttsx3: SAPI on
Windows, NSSpeech on macOS, espeak on Linux) | none (silent; narration shown as on-screen captions)."""
from __future__ import annotations
import hashlib, urllib.request, wave
from pathlib import Path

KOKORO_FILES = {"kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
                "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"}
KOKORO_VOICES = ["am_michael", "am_adam", "am_onyx", "am_puck", "af_heart", "af_bella", "af_nicole", "af_sarah", "bm_george", "bm_lewis", "bf_emma", "bf_isabella"]


def wav_seconds(p):
    with wave.open(str(p), "rb") as w: return w.getnframes() / float(w.getframerate())


class KokoroTTS:
    name = "kokoro"

    def __init__(self, models_dir, voice="am_michael", speed=1.0, cache=None, log=print):
        from kokoro_onnx import Kokoro
        md = Path(models_dir); md.mkdir(parents=True, exist_ok=True)
        for f, url in KOKORO_FILES.items():
            if not (md / f).exists():
                log(f"downloading voice model {f} (one time)…"); urllib.request.urlretrieve(url, md / f)
        self.k = Kokoro(str(md / "kokoro-v1.0.onnx"), str(md / "voices-v1.0.bin"))
        self.voice, self.speed = voice if voice in self.k.get_voices() else "am_michael", speed
        self.cache = Path(cache or md / "tts-cache"); self.cache.mkdir(parents=True, exist_ok=True)

    def with_speed(self, speed):
        o = object.__new__(KokoroTTS); o.__dict__.update(self.__dict__); o.speed = speed; return o

    def say(self, text):
        import soundfile as sf
        p = self.cache / (hashlib.sha1(f"k|{self.voice}|{self.speed:.2f}|{text}".encode()).hexdigest()[:16] + ".wav")
        if not p.exists():
            s, sr = self.k.create(text, voice=self.voice, speed=self.speed, lang="en-us")
            sf.write(str(p), s, sr, subtype="PCM_16")
        return p, wav_seconds(p)


class SystemTTS:
    name = "system"

    def __init__(self, cache, voice=None, speed=1.0, log=print):
        import pyttsx3  # noqa
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True); self.speed = speed; self.voice = voice

    def with_speed(self, speed):
        o = object.__new__(SystemTTS); o.__dict__.update(self.__dict__); o.speed = speed; return o

    def say(self, text):
        import pyttsx3
        p = self.cache / (hashlib.sha1(f"s|{self.speed:.2f}|{text}".encode()).hexdigest()[:16] + ".wav")
        if not p.exists():
            eng = pyttsx3.init(); eng.setProperty("rate", int(175 * self.speed))
            eng.save_to_file(text, str(p)); eng.runAndWait(); eng.stop()
        return p, wav_seconds(p)


class NoTTS:
    name = "none"

    def __init__(self, cache, wps=2.6, speed=1.0, **_):
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True); self.wps, self.speed = wps, speed

    def with_speed(self, speed):
        o = object.__new__(NoTTS); o.__dict__.update(self.__dict__); o.speed = speed; return o

    def say(self, text):
        sec = max(1.5, len(text.split()) / (self.wps * self.speed))
        p = self.cache / f"silence-{sec:.2f}.wav"
        if not p.exists():
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\x00\x00" * int(24000 * sec))
        return p, sec


def make_tts(ws, voice=None, log=print):
    pref, md = ws.s.tts, Path(ws.root) / ".models"
    order = [pref] if pref != "auto" else ["kokoro", "system", "none"]
    for name in order:
        try:
            if name == "kokoro": return KokoroTTS(md, voice or ws.s.voice, log=log)
            if name == "system": return SystemTTS(md / "tts-cache")
            if name == "none": return NoTTS(md / "tts-cache", ws.s.wps)
        except Exception as e:
            log(f"voice engine '{name}' unavailable: {type(e).__name__}: {e}")
    return NoTTS(md / "tts-cache", ws.s.wps)
