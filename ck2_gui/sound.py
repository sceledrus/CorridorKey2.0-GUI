"""The "all done" chime.

Design notes
  * The Qt Essentials wheel (what the GUI ships with) has no QtMultimedia, so sound is played with what the
    OS already has: `winsound` on Windows, `afplay` on macOS, `paplay`/`aplay`/`ffplay` on Linux.
  * Built-in chimes are synthesised with numpy (no audio files shipped, nothing to license) and cached as
    16-bit WAVs in the config folder.
  * A custom clip can be any format ffmpeg understands. WAV is used as-is; anything else is converted once
    to a WAV in the config folder, so playback is instant and does not depend on ffmpeg every time.
  * Playing a sound can never break a render: every public function swallows errors and reports a string.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from typing import Callable, Optional

import numpy as np

RATE = 44100

# name -> (label, one-line description). Order is the order shown in Settings.
CHIMES: dict[str, tuple[str, str]] = {
    "sparkle": ("Sparkle", "Three quick rising notes with a glassy tail."),
    "bell": ("Soft bell", "One warm, ringing bell."),
    "pop": ("Pop", "A short, dry 'bloop' - the most subtle one."),
    "fanfare": ("Little fanfare", "A bright four-note flourish."),
}
DEFAULT_CHIME = "sparkle"
CUSTOM_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus", ".aiff", ".aif")
MAX_CUSTOM_SECONDS = 20.0


# --------------------------------------------------------------------------------------------- synthesis
def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _tone(freq: float, dur: float, decay: float, harm=((1.0, 1.0), (2.0, 0.35), (3.0, 0.12)),
          attack: float = 0.004) -> np.ndarray:
    n = int(dur * RATE)
    t = np.arange(n) / RATE
    y = np.zeros(n)
    for mult, amp in harm:
        y += amp * np.sin(2 * math.pi * freq * mult * t)
    return y * _env(n, attack, decay)


def _place(buf: np.ndarray, snd: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * RATE)
    j = min(len(buf), i + len(snd))
    if i < len(buf):
        buf[i:j] += snd[: j - i] * gain


def synth(name: str) -> np.ndarray:
    """Mono float32 in [-1, 1]."""
    if name == "bell":
        buf = np.zeros(int(1.9 * RATE))
        _place(buf, _tone(880.0, 1.8, 0.55, ((1.0, 1.0), (2.76, 0.4), (5.4, 0.18), (8.9, 0.07))), 0.0)
    elif name == "pop":
        n = int(0.22 * RATE)
        t = np.arange(n) / RATE
        f = 420.0 + 780.0 * np.exp(-t / 0.035)                # quick downward pitch sweep -> 'bloop'
        phase = 2 * math.pi * np.cumsum(f) / RATE
        buf = np.sin(phase) * _env(n, 0.002, 0.06)
    elif name == "fanfare":
        buf = np.zeros(int(1.6 * RATE))
        for k, (f, at) in enumerate(((523.25, 0.0), (659.25, 0.13), (783.99, 0.26), (1046.5, 0.42))):
            _place(buf, _tone(f, 1.1 if k == 3 else 0.45, 0.35 if k == 3 else 0.18,
                              ((1.0, 1.0), (2.0, 0.5), (3.0, 0.3), (4.0, 0.15))), at, 0.9)
    else:                                                      # sparkle
        buf = np.zeros(int(1.5 * RATE))
        for f, at in ((987.77, 0.0), (1318.5, 0.09), (1975.5, 0.18)):
            _place(buf, _tone(f, 0.9, 0.22), at, 0.8)
        for f, at in ((2637.0, 0.30), (3951.0, 0.36)):         # glassy tail
            _place(buf, _tone(f, 0.6, 0.12, ((1.0, 1.0), (2.0, 0.2))), at, 0.35)
    peak = float(np.max(np.abs(buf))) or 1.0
    return (buf / peak * 0.85).astype(np.float32)


def write_wav(path: str, samples: np.ndarray, rate: int = RATE, volume: float = 1.0) -> None:
    """16-bit mono WAV. `volume` is baked in (0..1) so no player-side volume control is needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    x = np.clip(samples.astype(np.float32) * float(max(0.0, min(1.0, volume))), -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------------------------- custom audio
def wav_info(path: str) -> Optional[tuple[int, int, int, float]]:
    """(channels, sample width bytes, rate, seconds) for a PCM WAV, or None if it is not one winsound can play."""
    try:
        with wave.open(path, "rb") as w:
            return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, OSError):
        return None


def find_ffmpeg(hint: str = "") -> str:
    if hint and os.path.isfile(hint):
        return hint
    return shutil.which("ffmpeg") or ""


def prepare_custom(src: str, dest_dir: str, ffmpeg: str = "", volume: float = 1.0) -> tuple[str, str]:
    """Turn the user's clip into a short, cached, playable WAV. Returns (wav_path, message).

    wav_path is "" when it can't be done; the message then says why in plain words.
    """
    if not src or not os.path.isfile(src):
        return "", "The chosen audio file could not be found."
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, "custom_done.wav")
    ext = os.path.splitext(src)[1].lower()
    info = wav_info(src) if ext == ".wav" else None
    if info and info[1] in (1, 2) and info[3] <= MAX_CUSTOM_SECONDS:
        try:                                                   # plain PCM wav: copy untouched
            shutil.copyfile(src, out)
            return out, "Using your file as it is."
        except OSError as e:
            return "", f"Could not copy the audio file: {e}"
    ff = find_ffmpeg(ffmpeg)
    if not ff:
        why = "that WAV format" if ext == ".wav" else f"{ext or 'that'} files"
        return "", (f"Playing {why} needs ffmpeg to convert it once, and ffmpeg was not found. "
                    "Set the ffmpeg path in Settings > General, or pick a standard 16-bit .wav file.")
    cmd = [ff, "-y", "-v", "error", "-i", src, "-vn", "-t", f"{MAX_CUSTOM_SECONDS:g}",
           "-ac", "2", "-ar", str(RATE), "-c:a", "pcm_s16le", out]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=flags)
    except (OSError, subprocess.SubprocessError) as e:
        return "", f"ffmpeg could not run: {e}"
    if r.returncode != 0 or not os.path.isfile(out):
        tail = (r.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        return "", f"ffmpeg could not read that file ({tail[0]})."
    msg = "Converted to WAV once"
    if (wav_info(out) or (0, 0, 0, 0))[3] >= MAX_CUSTOM_SECONDS - 0.05:
        msg += f" (trimmed to the first {MAX_CUSTOM_SECONDS:g} seconds)"
    return out, msg + "."


# --------------------------------------------------------------------------------------------- playback
def _spawn(cmd: list[str]) -> bool:
    try:
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(cmd, **kw)
        return True
    except OSError:
        return False


def play_file(path: str) -> bool:
    """Fire-and-forget. Returns False if there was no way to play it."""
    if not path or not os.path.isfile(path):
        return False
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        if sys.platform == "darwin":
            return _spawn(["afplay", path])
        for exe, args in (("paplay", []), ("pw-play", []), ("aplay", ["-q"]),
                          ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"])):
            if shutil.which(exe):
                return _spawn([exe, *args, path])
    except Exception:
        pass
    return False


class SoundPlayer:
    """Owns the cached files and the choice of backend. `backend` can be swapped for tests."""

    def __init__(self, cache_dir: str, backend: Optional[Callable[[str], bool]] = None):
        self.cache_dir = cache_dir
        self.backend = backend or play_file
        self.last_message = ""
        self.last_path = ""

    def chime_path(self, name: str, volume: float = 1.0) -> str:
        name = name if name in CHIMES else DEFAULT_CHIME
        v = int(round(max(0.0, min(1.0, volume)) * 100))
        path = os.path.join(self.cache_dir, f"chime_{name}_{v}.wav")
        if not os.path.isfile(path):
            write_wav(path, synth(name), volume=v / 100.0)
        return path

    def resolve(self, chime: str, custom_path: str, use_custom: bool, volume: float, ffmpeg: str = "") -> str:
        """Which WAV would play right now ("" = nothing). Falls back to the built-in chime if the clip fails."""
        self.last_message = ""
        if use_custom and custom_path:
            wav, msg = prepare_custom(custom_path, self.cache_dir, ffmpeg)
            if wav:
                # volume for custom clips is applied by re-writing samples (only for plain PCM we can read)
                scaled = self._scaled(wav, volume)
                self.last_message = msg
                return scaled
            self.last_message = msg + " The standard sound is used instead."
        try:
            return self.chime_path(chime, volume)
        except OSError as e:
            self.last_message = f"Could not create the sound file: {e}"
            return ""

    def _scaled(self, wav: str, volume: float) -> str:
        v = max(0.0, min(1.0, volume))
        if v >= 0.995:
            return wav
        out = os.path.join(self.cache_dir, f"custom_done_{int(round(v * 100))}.wav")
        try:
            with wave.open(wav, "rb") as r:
                nch, sw, rate, n = r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getnframes()
                raw = r.readframes(n)
            if sw == 2:
                x = np.frombuffer(raw, "<i2").astype(np.float32) * v
                data = np.clip(x, -32768, 32767).astype("<i2").tobytes()
            elif sw == 1:
                x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) * v + 128.0
                data = np.clip(x, 0, 255).astype(np.uint8).tobytes()
            else:
                return wav
            with wave.open(out, "wb") as w:
                w.setnchannels(nch)
                w.setsampwidth(sw)
                w.setframerate(rate)
                w.writeframes(data)
            return out
        except (wave.Error, OSError, EOFError):
            return wav

    def play(self, chime: str = DEFAULT_CHIME, custom_path: str = "", use_custom: bool = False,
             volume: float = 0.8, ffmpeg: str = "") -> bool:
        path = self.resolve(chime, custom_path, use_custom, volume, ffmpeg)
        self.last_path = path
        if not path:
            return False
        ok = False
        try:
            ok = bool(self.backend(path))
        except Exception as e:                                  # a broken audio device must not crash the app
            self.last_message = f"Playback failed: {e}"
        if not ok and not self.last_message:
            self.last_message = "No audio player was found on this computer."
        return ok


def pack_check(path: str) -> bool:
    """True if `path` is a valid 16-bit PCM WAV with some non-silent samples (used by tests)."""
    info = wav_info(path)
    if not info or info[1] != 2:
        return False
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
    return bool(len(raw)) and any(struct.unpack_from("<h", raw, i)[0] for i in range(0, min(len(raw), 40000), 2))
