"""Click-to-select a subject: turns "keep this / remove that" markers into a rough black-and-white matte.

That matte is written as a first-frame hint for CorridorKey (README: "First-Frame Hint ... gives the model a
clear object identity at the beginning of the shot"). It is deliberately a *rough* hint - the model does the
real work on hair, motion blur and edges - so this uses classic OpenCV GrabCut, which needs no model, no GPU
and runs in a fraction of a second.

How a selection is made
  1. Seeds: a disk around every "keep" click is definite foreground, a disk around every "remove" click is
     definite background, and the frame border is background.
  2. Prior: if the border is one flat colour (a green/blue screen), everything that is not screen coloured is
     treated as probably-foreground; otherwise the colour region around each keep click is.
  3. GrabCut refines that.
  4. Only the connected regions you actually clicked are kept, so other people or props in the frame drop out.
  5. Optional grow/shrink and edge softness, then the matte is scaled back to the frame size.

Qt-free (numpy + OpenCV only).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

Marker = Sequence[float]     # (x, y, sign): x, y normalised to the frame, sign +1 keep / -1 remove

WORK_SIZE = 640              # longest side GrabCut runs at
OVERLAY_SIZE = 1280          # longest side of the on-screen tint


@dataclass
class SubjectResult:
    matte: np.ndarray        # float32 H x W in [0, 1], white = subject, same size as the input frame
    coverage: float          # fraction of the frame that is subject
    screen_found: bool       # a flat-colour backdrop was detected along the frame edge
    regions: int             # how many separate regions were kept


def _disk(shape: tuple[int, int], cx: float, cy: float, r: float) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    cv2.circle(m, (int(round(cx)), int(round(cy))), max(1, int(round(r))), 1, -1)
    return m.astype(bool)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    inv = (~mask).astype(np.uint8) * 255
    ff = np.zeros((h + 2, w + 2), np.uint8)
    # flood the outside; whatever stays unfilled in `inv` is a hole inside the subject
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if inv[seed[1], seed[0]] == 255:
            cv2.floodFill(inv, ff, seed, 128)
    return mask | (inv == 255)


def segment_subject(rgb: np.ndarray, markers: Sequence[Marker], grow: float = 0.0, soft: float = 0.0,
                    iters: int = 4) -> SubjectResult:
    """rgb: H x W x 3 uint8. grow / soft are percentages of the frame height (grow < 0 shrinks)."""
    if rgb is None or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("segment_subject needs an RGB frame")
    h, w = rgb.shape[:2]
    sc = min(1.0, WORK_SIZE / float(max(h, w)))
    sw, sh = max(8, int(round(w * sc))), max(8, int(round(h * sc)))
    short = min(sh, sw)
    r = max(3.0, 0.014 * short)

    # Markers are read in the order they were placed; a click of the opposite kind on (nearly) the same spot
    # cancels the earlier one, so right-clicking where you left-clicked simply undoes it.
    placed: list[tuple[float, float, int]] = []
    for m in markers:
        x, y, sg = float(m[0]) * (sw - 1), float(m[1]) * (sh - 1), (1 if m[2] > 0 else -1)
        placed = [q for q in placed if not (q[2] != sg and (q[0] - x) ** 2 + (q[1] - y) ** 2 < (2.5 * r) ** 2)]
        placed.append((x, y, sg))
    kp = [(x, y) for x, y, sg in placed if sg > 0]
    dp = [(x, y) for x, y, sg in placed if sg < 0]
    if not kp:
        return SubjectResult(np.zeros((h, w), np.float32), 0.0, False, 0)

    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA) if sc < 1.0 else rgb.copy()
    bgr = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    smooth = cv2.GaussianBlur(bgr, (0, 0), 1.2)
    lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB).astype(np.float32)

    # ---- 1. is the frame edge a flat backdrop (a green / blue screen)?
    band = max(3, int(0.03 * short))
    edge = np.zeros((sh, sw), bool)
    edge[:band, :] = edge[-band:, :] = edge[:, :band] = edge[:, -band:] = True
    border_lab = lab[edge]
    med = np.median(border_lab, axis=0)
    mad = np.median(np.abs(border_lab - med), axis=0)
    screen_found = bool(max(mad[1], mad[2]) < 6.0)
    screen = np.zeros((sh, sw), bool)
    if screen_found:
        d = np.sqrt((lab[..., 1] - med[1]) ** 2 + (lab[..., 2] - med[2]) ** 2 + 0.25 * (lab[..., 0] - med[0]) ** 2)
        screen = d < max(16.0, 4.0 * float(max(mad[1], mad[2])))

    # ---- 2. GrabCut seed mask
    gc = np.full((sh, sw), cv2.GC_PR_BGD, np.uint8)
    if screen_found:
        gc[~screen] = cv2.GC_PR_FGD
        gc[screen] = cv2.GC_BGD
    else:
        reach = max(r * 3.0, 0.30 * short)
        for cx, cy in kp:                                   # colour region around each keep click
            ff = np.zeros((sh + 2, sw + 2), np.uint8)
            cv2.floodFill(smooth.copy(), ff, (int(cx), int(cy)), (0, 0, 0), (14, 14, 14), (14, 14, 14),
                          4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
            region = ff[1:-1, 1:-1] > 0
            gc[region & _disk((sh, sw), cx, cy, reach)] = cv2.GC_PR_FGD
    gc[edge] = cv2.GC_BGD
    drop_mask = np.zeros((sh, sw), bool)                    # everything the user said to remove
    for cx, cy in dp:                                       # the colour region around a remove click, too
        ff = np.zeros((sh + 2, sw + 2), np.uint8)
        cv2.floodFill(smooth.copy(), ff, (int(cx), int(cy)), (0, 0, 0), (14, 14, 14), (14, 14, 14),
                      4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
        region = (ff[1:-1, 1:-1] > 0) & _disk((sh, sw), cx, cy, max(r * 3.0, 0.25 * short))
        drop_mask |= region | _disk((sh, sw), cx, cy, r * 1.6)
    gc[drop_mask] = cv2.GC_BGD
    keep_disks = np.zeros((sh, sw), bool)
    for cx, cy in kp:
        disk = _disk((sh, sw), cx, cy, r)
        keep_disks |= disk
        gc[disk] = cv2.GC_FGD
    if not (gc == cv2.GC_BGD).any():
        gc[0, :] = cv2.GC_BGD

    cv2.setRNGSeed(1234)                                    # GrabCut seeds k-means from a global RNG: same clicks, same matte
    bg_model = np.zeros((1, 65), np.float64)
    fg_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, gc, None, bg_model, fg_model, max(1, int(iters)), cv2.GC_INIT_WITH_MASK)
        fg = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    except cv2.error:                                       # degenerate image: fall back to the seeds
        fg = keep_disks.copy()

    # ---- 3. clean up, then keep only the regions that were clicked
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    fg |= keep_disks
    fg = _fill_holes(fg)
    n, labels = cv2.connectedComponents(fg.astype(np.uint8), connectivity=8)
    chosen: set[int] = set()
    forced = np.zeros((sh, sw), bool)
    for cx, cy in kp:
        x0, x1 = int(max(cx - 2 * r, 0)), int(min(cx + 2 * r + 1, sw))
        y0, y1 = int(max(cy - 2 * r, 0)), int(min(cy + 2 * r + 1, sh))
        win = labels[y0:y1, x0:x1]
        ids, counts = np.unique(win[win > 0], return_counts=True)
        if len(ids):
            chosen.add(int(ids[np.argmax(counts)]))
        else:
            forced |= _disk((sh, sw), cx, cy, r * 1.5)
    subject = np.isin(labels, list(chosen)) if chosen else np.zeros((sh, sw), bool)
    subject |= forced
    subject &= ~(drop_mask & ~keep_disks)                   # carve out whatever the user said to remove

    # ---- 4. grow / shrink, soften, scale back up
    k = int(round(abs(grow) / 100.0 * sh))
    if k > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
        op = cv2.dilate if grow > 0 else cv2.erode
        subject = op(subject.astype(np.uint8), kernel).astype(bool)
    matte = subject.astype(np.float32)
    sigma = max(0.8, soft / 100.0 * sh)                     # at least a hair of anti-aliasing
    matte = cv2.GaussianBlur(matte, (0, 0), sigma)
    if (sw, sh) != (w, h):
        matte = cv2.resize(matte, (w, h), interpolation=cv2.INTER_LINEAR)
    matte = np.clip(matte, 0.0, 1.0).astype(np.float32)
    return SubjectResult(matte, float((matte > 0.5).mean()), screen_found, len(chosen) + int(forced.any()))


def write_hint_png(path: str, matte: np.ndarray) -> None:
    """8-bit single-channel PNG (white = subject). imencode + tofile so non-ASCII Windows paths work."""
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ok, buf = cv2.imencode(".png", (np.clip(matte, 0, 1) * 255.0 + 0.5).astype(np.uint8))
    if not ok:
        raise RuntimeError("Could not encode the hint image")
    buf.tofile(path)


def make_overlay(matte: np.ndarray, rgb: tuple[int, int, int] = (43, 196, 79),
                 alpha: float = 0.42) -> np.ndarray:
    """RGBA tint + outline for the viewer (built at reduced size; Qt scales it to the frame)."""
    h, w = matte.shape[:2]
    sc = min(1.0, OVERLAY_SIZE / float(max(h, w)))
    m = cv2.resize(matte, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA) if sc < 1 else matte
    out = np.zeros(m.shape[:2] + (4,), np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = rgb
    out[..., 3] = np.clip(m * alpha * 255.0, 0, 255).astype(np.uint8)
    contours, _ = cv2.findContours((m > 0.5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (rgb[0], rgb[1], rgb[2], 255), 2)
    return out


def read_gray(path: str) -> Optional[np.ndarray]:
    """Read an image as float32 [0,1] gray (used by tests / tooling)."""
    buf = np.fromfile(path, np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return None if img is None else img.astype(np.float32) / 255.0
