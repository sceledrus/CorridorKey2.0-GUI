"""Everything the viewers need to show for one clip: its input, optional hint,
and whatever outputs infer.py has written. Qt-free."""
from __future__ import annotations

import os
from typing import Optional

from . import sources as S
from .model import Clip, discover_outputs

# (key, label shown on the tab)
MODES = [("input", "INPUT"), ("hint", "HINT"), ("fg", "FG"),
         ("alpha", "MATTE"), ("checker", "COMP"), ("cutout", "PROC")]
OUTPUT_MODES = ("fg", "alpha", "checker", "cutout")


class ClipMedia:
    def __init__(self, clip: Clip):
        self.clip = clip
        self.input: Optional[S.FrameSource] = None
        self.hint: Optional[S.FrameSource] = None
        self.hint_still = None
        self.outputs: dict[str, S.FrameSource] = {}
        self.out_paths: dict[str, str] = {}
        self.error = ""
        self.reload_input()
        self.reload_hint()

    # -- opening ---------------------------------------------------------
    def reload_input(self) -> None:
        if self.input is not None:
            self.input.close()
        s = self.clip.settings
        try:
            self.input = S.open_source(self.clip.path, linear=s.frame_linear, fps=s.frame_fps)
            self.error = ""
        except Exception as e:  # unreadable file: viewer shows the message
            self.input, self.error = None, str(e)

    def reload_hint(self) -> None:
        if self.hint is not None:
            self.hint.close()
        self.hint, self.hint_still = None, None
        s = self.clip.settings
        if not s.hint_path or not os.path.exists(s.hint_path):
            return
        try:
            if s.hint_mode == "video":
                self.hint = S.open_source(s.hint_path)
            elif s.hint_mode in ("first", "marker"):
                if os.path.isdir(s.hint_path):
                    src = S.open_source(s.hint_path)
                    self.hint_still = src.frame(0)
                    src.close()
                elif s.hint_mode == "marker":
                    # written by this app into the config folder, which may have non-ASCII characters on
                    # Windows (the user name), so read through numpy instead of cv2.imread
                    buf = S.np.fromfile(s.hint_path, S.np.uint8)
                    img = S.cv2.imdecode(buf, S.cv2.IMREAD_UNCHANGED)
                    self.hint_still = S.to_display(img)
                else:
                    img = S.cv2.imread(s.hint_path, S.cv2.IMREAD_UNCHANGED | S.cv2.IMREAD_ANYDEPTH)
                    self.hint_still = S.to_display(img, linear=s.hint_path.lower().endswith(".exr"))
        except Exception:
            self.hint, self.hint_still = None, None

    def scan_outputs(self, out_dir: str) -> None:
        for src in self.outputs.values():
            src.close()
        self.outputs, self.out_paths = {}, {}
        if not out_dir:
            return
        paths = discover_outputs(out_dir, self.clip.name, prefer=self.clip.settings.output_format)
        for key, path in paths.items():
            try:
                is_dir = os.path.isdir(path)
                self.outputs[key] = S.open_source(path, linear=is_dir)  # EXR output is scene-linear
                self.out_paths[key] = path
            except Exception:
                continue

    def close(self) -> None:
        for src in (self.input, self.hint, *self.outputs.values()):
            if src is not None:
                src.close()

    # -- queries ---------------------------------------------------------
    @property
    def count(self) -> int:
        return self.input.count if self.input else self.clip.frames

    def available(self, mode: str) -> bool:
        if mode == "input":
            return self.input is not None
        if mode == "hint":
            return self.hint is not None or self.hint_still is not None
        return mode in self.outputs

    def has_outputs(self) -> bool:
        return bool(self.outputs)

    def frame(self, mode: str, i: int) -> tuple[Optional[object], str]:
        """-> (rgb uint8 array | None, note shown when None)."""
        if mode == "input":
            fr = self.input.frame(i) if self.input else None
            return (fr[0], "") if fr else (None, self.error or "CANNOT READ FRAME")
        if mode == "hint":
            if self.hint_still is not None:
                return self.hint_still[0], ""
            fr = self.hint.frame(i) if self.hint else None
            return (fr[0], "") if fr else (None, "NO HINT FOR THIS FRAME")
        src = self.outputs.get(mode)
        if src is None:
            return None, "NO OUTPUT YET - RUN INFERENCE"
        j = i - self.clip.ran_start
        if j < 0 or j >= src.count:
            return None, "OUTSIDE THE PROCESSED RANGE"
        fr = src.frame(j)
        if fr is None:
            return None, "CANNOT READ OUTPUT FRAME"
        rgb, alpha = fr
        if mode == "cutout":
            if alpha is None and "alpha" in self.outputs:
                m = self.outputs["alpha"].frame(j)
                if m is not None:
                    alpha = m[0][..., 0]
            if alpha is not None:
                return S.composite_over_checker(rgb, alpha), ""
        return rgb, ""
