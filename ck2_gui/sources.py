"""Frame access for the viewers (OpenCV + numpy only, no Qt).

Everything here returns *display* pixels: 8-bit RGB (plus optional 8-bit
alpha). Float EXR data is tone-mapped with the sRGB curve when the source is
scene-linear. This is review-grade only; the files on disk are never modified.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# Must be set before cv2 is imported for EXR reading to work.
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

# opencv-python (non-headless) on Linux ships its own Qt plugins and points Qt at
# them, which breaks PySide6. Drop those overrides if cv2 set them.
for _k in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR"):
    if "cv2" in os.environ.get(_k, "").replace("\\", "/"):
        os.environ.pop(_k, None)

Frame = tuple  # (rgb uint8 HxWx3, alpha uint8 HxW | None)


def srgb_encode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def to_display(img: Optional[np.ndarray], linear: bool = False) -> Optional[Frame]:
    """OpenCV image (BGR/BGRA/gray, any depth) -> (rgb_u8, alpha_u8|None)."""
    if img is None:
        return None
    if img.dtype == np.uint8:
        f = img
    elif img.dtype == np.uint16:
        f = (img >> 8).astype(np.uint8)
    else:
        a = img.astype(np.float32)
        a = np.nan_to_num(a, nan=0.0, posinf=1.0, neginf=0.0)
        color = a
        if a.ndim == 3 and a.shape[2] == 4:
            color = a[..., :3]
        if linear:
            color = srgb_encode(color)
        else:
            color = np.clip(color, 0.0, 1.0)
        if a.ndim == 3 and a.shape[2] == 4:
            a = np.concatenate([color, np.clip(a[..., 3:4], 0.0, 1.0)], axis=2)
        else:
            a = color
        f = (a * 255.0 + 0.5).astype(np.uint8)
    alpha = None
    if f.ndim == 2:
        rgb = np.repeat(f[..., None], 3, axis=2)
    elif f.shape[2] == 1:
        rgb = np.repeat(f, 3, axis=2)
    elif f.shape[2] == 4:
        rgb = cv2.cvtColor(f, cv2.COLOR_BGRA2RGB)
        alpha = np.ascontiguousarray(f[..., 3])
    else:
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray(rgb), alpha


_checker_cache: dict = {}


def checker(h: int, w: int, cell: int = 16) -> np.ndarray:
    key = (h, w, cell)
    if key not in _checker_cache:
        ys, xs = np.mgrid[0:h, 0:w]
        on = ((ys // cell) + (xs // cell)) % 2 == 0
        c = np.where(on, 96, 64).astype(np.uint8)
        _checker_cache.clear()
        _checker_cache[key] = np.repeat(c[..., None], 3, axis=2)
    return _checker_cache[key]


def composite_over_checker(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    if alpha.shape[:2] != (h, w):
        alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    a = (alpha.astype(np.float32) / 255.0)[..., None]
    bg = checker(h, w).astype(np.float32)
    return (rgb.astype(np.float32) * a + bg * (1.0 - a) + 0.5).astype(np.uint8)


class FrameSource:
    kind = "base"
    path = ""
    count = 0
    fps = 24.0
    size = (0, 0)  # (w, h)
    linear = False

    def frame(self, i: int) -> Optional[Frame]:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        pass


class VideoSource(FrameSource):
    kind = "video"

    def __init__(self, path: str, cache: int = 16):
        self.path = path
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open video: {path}")
        self.count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 24.0
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                     int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._pos = 0  # index of the next frame cap.read() will return
        self._cache: OrderedDict[int, Optional[Frame]] = OrderedDict()
        self._cache_max = cache

    def frame(self, i: int) -> Optional[Frame]:
        if i in self._cache:
            self._cache.move_to_end(i)
            return self._cache[i]
        if i < 0 or (self.count and i >= self.count):
            return None
        if i != self._pos:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, img = self._cap.read()
        self._pos = i + 1 if ok else int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        out = to_display(img) if ok else None
        self._cache[i] = out
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return out

    def close(self) -> None:
        self._cap.release()
        self._cache.clear()


class SequenceSource(FrameSource):
    kind = "sequence"

    def __init__(self, path: str, linear: bool = False, fps: float = 24.0, cache: int = 8):
        self.path = path
        self.linear = linear
        self.fps = fps
        # identical ordering to corridorkey.video_io.frame_paths()
        paths: list[str] = []
        for ext in ("*.exr", "*.png", "*.jpg", "*.jpeg"):
            paths.extend(str(p) for p in Path(path).glob(ext))
        self.files = sorted(paths)
        if not self.files:
            raise RuntimeError(f"No frames found in {path}")
        self.count = len(self.files)
        first = cv2.imread(self.files[0], cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        if first is None:
            if self.files[0].lower().endswith(".exr") and not cv2.haveImageReader(self.files[0]):
                raise RuntimeError(
                    "This OpenCV build cannot read EXR files. CorridorKey needs an EXR-capable "
                    "opencv-python as well (pip install --force-reinstall \"opencv-python>=4.11,<4.12\" "
                    "if you installed a build without OpenEXR).")
            raise RuntimeError(f"Could not read {self.files[0]}")
        self.size = (first.shape[1], first.shape[0])
        self._cache: OrderedDict[int, Optional[Frame]] = OrderedDict()
        self._cache_max = cache

    def frame(self, i: int) -> Optional[Frame]:
        if i in self._cache:
            self._cache.move_to_end(i)
            return self._cache[i]
        if i < 0 or i >= self.count:
            return None
        img = cv2.imread(self.files[i], cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        out = to_display(img, linear=self.linear and self.files[i].lower().endswith(".exr"))
        self._cache[i] = out
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return out

    def close(self) -> None:
        self._cache.clear()


def open_source(path: str, linear: bool = False, fps: float = 24.0) -> FrameSource:
    if os.path.isdir(path):
        return SequenceSource(path, linear=linear, fps=fps)
    return VideoSource(path)


def probe(path: str) -> dict:
    """frames / fps / size of a clip, cheap enough to call at import time."""
    src = open_source(path)
    try:
        info = {"frames": src.count, "fps": float(src.fps),
                "width": src.size[0], "height": src.size[1]}
        probe_idx = min(max(src.count // 10, 0), max(src.count - 1, 0))
        fr = src.frame(probe_idx) or src.frame(0)
        info["thumb"] = thumbnail(fr[0]) if fr else None
        return info
    finally:
        src.close()


def thumbnail(rgb: np.ndarray, width: int = 192) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = width / float(w)
    return cv2.resize(rgb, (width, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
