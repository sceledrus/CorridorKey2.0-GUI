"""Data model and command construction. No Qt and no OpenCV in here, so it can
be unit-tested anywhere and mirrors ``run_interactive.py`` / ``infer.py``."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

FROZEN = bool(getattr(sys, "frozen", False))


def _find_repo_root() -> Path:
    """The CorridorKey folder (the one with infer.py). Normally the parent of this package; for the
    standalone exe it is the folder the exe sits in, or the nearest parent that contains infer.py."""
    if FROZEN:
        here = Path(sys.executable).resolve().parent
        for d in (here, *list(here.parents)[:3]):
            if (d / "infer.py").exists():
                return d
        return here
    return Path(__file__).resolve().parent.parent


REPO_ROOT = _find_repo_root()

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
# Exactly the extensions corridorkey.video_io.frame_paths() reads.
FRAME_EXTS = {".exr", ".png", ".jpg", ".jpeg"}
HINT_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".exr"}

OUTPUT_KEYS = ("alpha", "fg", "checker", "cutout")
OUTPUT_LABELS = {"alpha": "Matte", "fg": "FG", "checker": "Comp", "cutout": "Cutout"}
# Same Hann presets run_interactive.py offers, plus the 1/1 floor from the README.
HANN_PRESETS = [
    ("80 / 40  max continuity", 80, 40),
    ("48 / 24  high VRAM", 48, 24),
    ("24 / 12  medium VRAM", 24, 12),
    ("8 / 4  low VRAM", 8, 4),
    ("1 / 1  single frame", 1, 1),
]


# --------------------------------------------------------------------------
# settings + clips
# --------------------------------------------------------------------------
@dataclass
class Settings:
    # hint
    hint_mode: str = "none"          # none | marker | first | video
    hint_path: str = ""
    hint_quality: float = 0.95
    carry_quality: float = 0.95
    no_carry: bool = False
    # subject marker (hint_mode == "marker"): clicks -> rough matte -> first-frame hint
    markers: list = field(default_factory=list)   # [[x, y, +1 keep | -1 remove], ...] normalised to the frame
    marker_frame: int = -1                        # input frame the markers were placed on
    marker_grow: int = 0                          # tenths of a percent of frame height (negative shrinks)
    marker_soft: int = 8                          # edge softness, tenths of a percent of frame height
    # inference
    despill: float = 0.5
    cutout_linear: bool = False
    frame_linear: bool = False       # frame sequences only: scene-linear input
    frame_fps: float = 24.0
    model_scale: float = 1.0
    # outputs
    outputs: list = field(default_factory=lambda: list(OUTPUT_KEYS))
    output_format: str = "video"     # video | exr
    exr_dtype: str = "half"          # half | float
    out_dir: str = ""                # per-clip override, "" = default
    # memory
    auto_vram: bool = True
    low_vram: bool = False
    hann_chunk: int = 48
    hann_stride: int = 24
    stage2_batch: int = 1
    temp_dir: str = ""               # "" = infer.py default
    # partial clips
    num_frames: int = 0              # 0 = whole clip
    start_mode: str = "begin"        # begin | middle | random_middle
    seed: int = 0
    # video encoding (ignored for EXR)
    codec: str = "libx264"
    crf: int = 12
    preset: str = "medium"
    pix_fmt: str = "yuv444p10le"
    bitrate: str = ""                # "" = use CRF; e.g. "50M" or "8000k" replaces CRF
    threads: int = 2                 # ffmpeg threads

    def copy(self) -> "Settings":
        return Settings.from_dict(asdict(self))

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        known = {f.name for f in fields(Settings)}
        s = Settings(**{k: v for k, v in (d or {}).items() if k in known})
        s.outputs = [o for o in s.outputs if o in OUTPUT_KEYS]
        clean = []
        for m in s.markers if isinstance(s.markers, list) else []:
            try:
                x, y, sign = float(m[0]), float(m[1]), (1 if int(m[2]) > 0 else -1)
            except (TypeError, ValueError, IndexError):
                continue
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                clean.append([x, y, sign])
        s.markers = clean
        return s


@dataclass
class Clip:
    path: str                        # what is passed to infer.py --input
    kind: str                        # video | sequence
    name: str                        # raw_clip_name(path): prefix of output files
    frames: int = 0
    fps: float = 24.0
    width: int = 0
    height: int = 0
    settings: Settings = field(default_factory=Settings)
    status: str = "READY"            # READY QUEUED RUNNING COMPLETE ERROR CANCELLED
    message: str = ""
    ran_start: int = 0               # first input frame of the last completed run
    ran_dir: str = ""                # output folder of the last run
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["status"] in ("QUEUED", "RUNNING"):
            d["status"] = "READY"
        return d

    @staticmethod
    def from_dict(d: dict) -> "Clip":
        known = {f.name for f in fields(Clip)}
        d = {k: v for k, v in d.items() if k in known}
        d["settings"] = Settings.from_dict(d.get("settings", {}))
        return Clip(**d)


def raw_clip_name(path: str) -> str:
    """Same rule as corridorkey.video_io.raw_clip_name (output file prefix)."""
    norm = os.path.normpath(str(path))
    name = os.path.splitext(os.path.basename(norm))[0]
    if name.lower() in {"input", "frames", "rgb"}:
        return os.path.basename(os.path.dirname(norm)) or name
    return name


def default_output_dir(clip: Clip, global_out_dir: str = "") -> str:
    if clip.settings.out_dir:
        return clip.settings.out_dir
    folder = f"out_{clip.name}"
    if global_out_dir:
        return os.path.join(global_out_dir, folder)
    return os.path.join(os.path.dirname(os.path.normpath(clip.path)), folder)


def processed_range(total: int, kind: str, s: Settings) -> tuple[int, int]:
    """(first_frame, frame_count) that infer.py will actually process.

    Mirrors probe_video_meta / probe_frame_dir_meta: frame directories always
    take the first N frames; videos honour --start_mode.
    """
    if total <= 0:
        return 0, 0
    n = total if s.num_frames <= 0 else min(s.num_frames, total)
    start = 0
    max_start = max(total - n, 0)
    if kind == "video" and s.num_frames > 0 and max_start > 0:
        if s.start_mode == "middle":
            start = max_start // 2
        elif s.start_mode == "random_middle":
            import numpy as np
            lo, hi = max_start // 4, (3 * max_start) // 4
            start = int(np.random.default_rng(int(s.seed)).integers(lo, hi + 1))
    return start, n


# --------------------------------------------------------------------------
# import discovery (same conventions as run_interactive.py / README)
# --------------------------------------------------------------------------
@dataclass
class ImportItem:
    path: str
    kind: str
    hint_mode: str = "none"
    hint_path: str = ""
    linear_default: bool = False


def _has_frames(d: Path) -> bool:
    try:
        return any(p.is_file() and p.suffix.lower() in FRAME_EXTS for p in d.iterdir())
    except OSError:
        return False


def _is_hint_companion(p: Path) -> bool:
    low = p.stem.lower()
    return "_alphahint" in low or "framehint" in low


def find_alpha_hint_video(video: Path) -> Optional[Path]:
    prefix = f"{video.stem.lower()}_alphahint"
    try:
        for item in sorted(video.parent.iterdir()):
            if (item.is_file() and item.suffix.lower() in VIDEO_EXTS | HINT_IMAGE_EXTS
                    and item.name.lower().startswith(prefix)):
                return item
    except OSError:
        pass
    return None


def find_first_frame_hint(video: Path) -> Optional[Path]:
    base = video.stem.lower()
    frame_hints, legacy = [], []
    try:
        for item in sorted(video.parent.iterdir()):
            if not item.is_file() or item.suffix.lower() not in HINT_IMAGE_EXTS:
                continue
            low = item.stem.lower()
            if not low.startswith(base):
                continue
            rest = low[len(base):].lstrip("_- ")
            if rest.startswith("framehint"):
                frame_hints.append(item)
            elif rest.startswith("alphahint"):
                legacy.append(item)
    except OSError:
        pass
    found = frame_hints or legacy
    return found[0] if found else None


def _video_item(p: Path) -> ImportItem:
    item = ImportItem(str(p), "video")
    hint = find_alpha_hint_video(p)
    if hint is not None and hint.suffix.lower() in VIDEO_EXTS:
        item.hint_mode, item.hint_path = "video", str(hint)
        return item
    first = find_first_frame_hint(p) or (hint if hint is not None else None)
    if first is not None:
        item.hint_mode, item.hint_path = "first", str(first)
    return item


def _sequence_item(frames_dir: Path, shot_dir: Optional[Path] = None) -> ImportItem:
    item = ImportItem(str(frames_dir), "sequence")
    for base in (shot_dir, frames_dir.parent):
        if base is None:
            continue
        for sub in ("AlphaHint", "alphahint", "Alphahint"):
            cand = base / sub
            if cand.is_dir() and _has_frames(cand):
                item.hint_mode, item.hint_path = "video", str(cand)
                break
        if item.hint_mode != "none":
            break
    try:
        first = sorted(p for p in frames_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in FRAME_EXTS)[0]
        item.linear_default = first.suffix.lower() == ".exr"
    except (OSError, IndexError):
        pass
    return item


def _dir_as_sequence(d: Path) -> Optional[ImportItem]:
    inp = next((c for c in (d / "Input", d / "input") if c.is_dir()), None)
    if inp is not None and _has_frames(inp):
        return _sequence_item(inp, shot_dir=d)
    if _has_frames(d):
        return _sequence_item(d)
    return None


def resolve_import(path: str) -> list[ImportItem]:
    """Turn a dropped path into clips. Folder-of-clips is expanded one level."""
    p = Path(path)
    if p.is_file():
        if p.suffix.lower() in VIDEO_EXTS and not _is_hint_companion(p):
            return [_video_item(p)]
        return []
    if not p.is_dir():
        return []
    seq = _dir_as_sequence(p)
    if seq is not None:
        return [seq]
    items: list[ImportItem] = []
    try:
        children = sorted(p.iterdir())
    except OSError:
        return []
    for c in children:
        if c.is_file() and c.suffix.lower() in VIDEO_EXTS and not _is_hint_companion(c):
            items.append(_video_item(c))
        elif c.is_dir() and c.name.lower() not in ("alphahint",) and not c.name.startswith("out_"):
            s = _dir_as_sequence(c)
            if s is not None:
                items.append(s)
    return items


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------
_DEFAULTS = Settings()


def validate(clip: Clip) -> list[str]:
    s, errs = clip.settings, []
    if not os.path.exists(clip.path):
        errs.append(f"Input not found: {clip.path}")
    if not s.outputs:
        errs.append("Select at least one output.")
    if s.hint_mode == "marker":
        if not any(m[2] > 0 for m in s.markers):
            errs.append("Subject Marker: left-click the subject in the INPUT view to place at least one 'keep' marker.")
        else:
            first, _n = processed_range(clip.frames, clip.kind, s)
            if s.marker_frame != first:
                errs.append(f"Subject Marker: your markers are on frame {s.marker_frame + 1}, but processing starts at "
                            f"frame {first + 1}. Go to frame {first + 1} and place them again (or change the frame range).")
            elif not s.hint_path or not os.path.exists(s.hint_path):
                errs.append("Subject Marker: the hint image has not been generated yet. Click the subject once more.")
    elif s.hint_mode in ("first", "video"):
        if not s.hint_path:
            errs.append("Hint mode is on but no hint path is set.")
        elif not os.path.exists(s.hint_path):
            errs.append(f"Hint not found: {s.hint_path}")
    if not s.auto_vram and (s.hann_chunk < 1 or s.hann_stride < 1
                            or s.hann_stride > s.hann_chunk):
        errs.append("Hann stride must be between 1 and the Hann chunk size.")
    if s.model_scale <= 0:
        errs.append("Model scale must be greater than 0.")
    return errs


def build_command(python: str, infer_script: str, clip: Clip, out_dir: str,
                  ffmpeg_bin: str = "") -> list[str]:
    s = clip.settings
    cmd = [python, infer_script, "--input", clip.path, "--output_dir", out_dir]

    if s.hint_mode in ("first", "marker") and s.hint_path:
        cmd += ["--hint_first_frame", s.hint_path, "--hint_quality", f"{s.hint_quality:g}",
                "--carry_hint_quality", f"{s.carry_quality:g}"]
    elif s.hint_mode == "video" and s.hint_path:
        cmd += ["--hint_video", s.hint_path, "--hint_quality", f"{s.hint_quality:g}"]
        if s.no_carry:
            cmd.append("--no_carry_hint")
        else:
            cmd += ["--carry_hint_quality", f"{s.carry_quality:g}"]

    cmd += ["--outputs", *[o for o in OUTPUT_KEYS if o in s.outputs]]
    cmd += ["--despill_strength", f"{s.despill:g}"]
    if s.cutout_linear and "cutout" in s.outputs and s.output_format == "video":
        cmd.append("--cutout_linear")
    if clip.kind == "sequence":
        if s.frame_linear:
            cmd.append("--frame_dir_linear")
        if s.frame_fps != _DEFAULTS.frame_fps:
            cmd += ["--frame_dir_fps", f"{s.frame_fps:g}"]
    if s.model_scale != 1.0:
        cmd += ["--model_scale", f"{s.model_scale:g}"]

    cmd += ["--output_format", s.output_format]
    if s.output_format == "exr":
        cmd += ["--exr_dtype", s.exr_dtype]
    else:
        if s.codec != _DEFAULTS.codec:
            cmd += ["--ffmpeg_codec", s.codec]
        if s.crf != _DEFAULTS.crf and not s.bitrate.strip():     # a bitrate replaces CRF in the runtime
            cmd += ["--crf", str(s.crf)]
        if s.preset != _DEFAULTS.preset:
            cmd += ["--preset", s.preset]
        if s.pix_fmt != _DEFAULTS.pix_fmt:
            cmd += ["--pix_fmt", s.pix_fmt]
        if s.bitrate.strip():
            cmd += ["--bitrate", s.bitrate.strip()]
        if s.threads != _DEFAULTS.threads:
            cmd += ["--ffmpeg_threads", str(max(1, int(s.threads)))]
    if ffmpeg_bin:
        cmd += ["--ffmpeg_bin", ffmpeg_bin]

    # Memory: with no flags infer.py measures free VRAM per clip (auto mode).
    if s.low_vram:
        cmd.append("--low_vram")
    if s.temp_dir and (s.low_vram or not s.auto_vram):
        cmd += ["--temp_dir", s.temp_dir]
    if not s.auto_vram:
        cmd += ["--hann_chunk", str(s.hann_chunk), "--hann_stride", str(s.hann_stride)]
    if s.stage2_batch != 1:
        cmd += ["--stage2_batch", str(s.stage2_batch)]

    if s.num_frames > 0:
        cmd += ["--num_frames", str(s.num_frames)]
        if clip.kind == "video":
            cmd += ["--start_mode", s.start_mode]
            if s.start_mode == "random_middle":
                cmd += ["--seed", str(s.seed)]
    return cmd


def find_python(repo_root: Path = REPO_ROOT) -> str:
    """The Python that runs infer.py. Prefer the repo's venv (as the drag-and-drop launchers do)."""
    for name in ("venv", ".venv", "env"):
        for cand in (repo_root / name / "Scripts" / "python.exe", repo_root / name / "bin" / "python"):
            if cand.exists():
                return str(cand)
    if FROZEN:      # sys.executable is this exe, not a Python: look for one on PATH, skipping the Store stub
        found = shutil.which("python")
        if found and "\\windowsapps\\" not in found.lower():
            return found
        return "python"
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")      # started via the launcher exe / pythonw
    return sys.executable


# --------------------------------------------------------------------------
# outputs on disk
# --------------------------------------------------------------------------
def discover_outputs(out_dir: str, name: str, prefer: str = "video") -> dict[str, str]:
    """Map output key -> video file or EXR folder written by infer.py."""
    found: dict[str, str] = {}
    d = Path(out_dir)
    if not d.is_dir():
        return found
    patterns = {
        "alpha": (f"{name}_alpha.mp4", f"{name}_alpha_exr"),
        "fg": (f"{name}_fg.mp4", f"{name}_fg_exr"),
        "checker": (f"{name}_checker_comp_despill*.mp4", f"{name}_checker_comp_despill*_exr"),
        "cutout": (f"{name}_cutout.mov", f"{name}_cutout_exr"),
    }
    for key, (vid_pat, exr_pat) in patterns.items():
        vids = sorted(d.glob(vid_pat), key=lambda p: p.stat().st_mtime, reverse=True)
        exrs = sorted((p for p in d.glob(exr_pat) if p.is_dir()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        order = (exrs, vids) if prefer == "exr" else (vids, exrs)
        for group in order:
            if group:
                found[key] = str(group[0])
                break
    return found


# --------------------------------------------------------------------------
# progress parsing (matches the lines corridorkey.runtime prints)
# --------------------------------------------------------------------------
class ProgressParser:
    RE_WIN = re.compile(r"window\s+(\d+)\s*/\s*(\d+)\s*\[(\d+):(\d+)\]")
    RE_STAGE1 = re.compile(r"Hann stage1:\s*chunk=(\d+),\s*stride=(\d+),\s*windows=(\d+)")
    RE_T = re.compile(r"\bT=(\d+)")
    RE_AUTO = re.compile(r"Auto VRAM:\s*(.*)")
    RE_WROTE = re.compile(r"wrote\s+(\d+)\s+output.*?\((\d+)\s+frames\s*@\s*(\d+)x(\d+)\)")

    def __init__(self, total_frames: int = 0, low_vram: bool = False):
        self.total = total_frames
        self.low_vram = low_vram
        self.phase = "STARTING"
        self.frame = 0
        self.fraction = 0.0
        self.window = (0, 0)
        self.auto_note = ""
        self.warnings: list[str] = []
        self.done = False

    def feed(self, line: str) -> bool:
        line = line.rstrip()
        if not line:
            return False
        if "Loading CorridorKey v2 runtime weights" in line:
            self.phase = "LOADING MODEL"
            return True
        m = self.RE_AUTO.search(line)
        if m:
            self.auto_note = m.group(1).strip()
            return True
        if "prepass" in line:
            self.phase = "ANALYSING"
            t = self.RE_T.search(line)
            if t:
                self.total = int(t.group(1))
            return True
        if self.RE_STAGE1.search(line):
            self.phase = "KEYING"
            return True
        m = self.RE_WIN.search(line)
        if m:
            i, n, _t0, t1 = (int(g) for g in m.groups())
            self.window = (i, n)
            self.frame = t1
            self.phase = "KEYING"
            frac = (t1 / self.total) if self.total else (i / max(n, 1))
            frac = min(max(frac, 0.0), 1.0)
            if self.low_vram:
                frac *= 0.85
                if i >= n:
                    self.phase = "RENDERING"
                    frac = 0.9
            self.fraction = frac
            return True
        m = self.RE_WROTE.search(line)
        if m:
            self.phase, self.fraction, self.done = "DONE", 1.0, True
            self.frame = int(m.group(2))
            return True
        if "[WARNING]" in line or "[ERROR]" in line:
            self.warnings.append(line.strip())
            return True
        return False


# --------------------------------------------------------------------------
# environment checks
# --------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _prefer(root: Path, stem: str) -> Path:
    st = root / f"{stem}.safetensors"
    pt = root / f"{stem}.pt"
    return pt if (not st.exists() and pt.exists()) else st


def preflight(repo_root: Path = REPO_ROOT, ffmpeg_bin: str = "ffmpeg",
              weights_override: str = "") -> list[Check]:
    checks: list[Check] = []
    assets = [
        ("CorridorKey 2.0 weights",
         Path(weights_override) if weights_override else _prefer(repo_root, "weights/corridorkey_v2")),
        ("Foundation stats", _prefer(repo_root, "weights/foundation_stats")),
        ("RVM checkpoint", repo_root / "vfms/rvm/pretrain_rvm_small16_256_204031069.npz"),
        ("MoGe checkpoint", repo_root / "vfms/moge/model.pt"),
        ("C-RADIO model", repo_root / "vfms/cradio/C-RADIOv4-SO400M"),
    ]
    for label, p in assets:
        checks.append(Check(label, p.exists(), str(p) if p.exists() else f"missing: {p}"))
    ff = shutil.which(ffmpeg_bin or "ffmpeg")
    checks.append(Check("ffmpeg", bool(ff), ff or "not found on PATH"))
    checks.append(Check("infer.py", (repo_root / "infer.py").exists(), str(repo_root / "infer.py")))
    return checks


def parse_nvidia_smi(text: str) -> Optional[tuple[str, float, float]]:
    """First GPU from `nvidia-smi --query-gpu=name,memory.used,memory.total
    --format=csv,noheader,nounits` -> (name, used_GB, total_GB)."""
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                return parts[0], float(parts[1]) / 1024.0, float(parts[2]) / 1024.0
            except ValueError:
                continue
    return None


# --------------------------------------------------------------------------
# privacy: take the user's name out of text that may be pasted into a bug report
# --------------------------------------------------------------------------
_USER_DIR_RE = re.compile(r"(?i)((?:[A-Z]:|\\\\\?\\[A-Z]:)?[\\/]+(?:Users|home)[\\/]+)[^\\/\"'<>|:*?\r\n]+")


def scrub(text: str) -> str:
    """Replace the account name inside paths (C:\\Users\\<name>\\..., /home/<name>/..., /Users/<name>/...) and the exact
    home folder with placeholders. Used for crash.log and for the 'copy for a bug report' buttons, so nothing a user
    pastes into a public issue says who they are. It cannot know every private word (a clip called my_birthday.mp4 stays),
    so people should still skim what they paste."""
    if not text:
        return text
    out = text
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        home = ""
    if len(home) > 3:
        for form in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
            out = re.sub(re.escape(form), "~", out, flags=re.I if os.name == "nt" else 0)
    return _USER_DIR_RE.sub(lambda m: m.group(1) + "<user>", out)


# --------------------------------------------------------------------------
# session persistence
# --------------------------------------------------------------------------
def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "CorridorKey2-GUI"
    legacy = base / "CorridrusKey2-GUI"        # folder used by the builds that were briefly called "Corridrus": copy it over once
    marker = d / ".migrated_from_legacy_name"
    d.mkdir(parents=True, exist_ok=True)
    if legacy.is_dir() and not marker.exists():
        try:
            shutil.copytree(legacy, d, dirs_exist_ok=True)
            marker.write_text("", encoding="utf-8")
        except OSError:
            pass
    return d


def save_session(clips: list[Clip], prefs: dict, path: Optional[Path] = None) -> None:
    path = path or (config_dir() / "session.json")
    data = {"version": 1, "prefs": prefs, "clips": [c.to_dict() for c in clips]}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_session(path: Optional[Path] = None) -> tuple[list[Clip], dict]:
    path = path or (config_dir() / "session.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    clips = []
    for d in data.get("clips", []):
        try:
            c = Clip.from_dict(d)
        except TypeError:
            continue
        if os.path.exists(c.path):
            clips.append(c)
    return clips, data.get("prefs", {})
