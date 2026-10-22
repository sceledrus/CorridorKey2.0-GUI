"""Dual viewer: INPUT on the left, switchable result on the right, with linked
pan/zoom and an optional A/B wipe."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from . import help_text as H
from . import theme as T
from .media import MODES, ClipMedia

MIN_ZOOM, MAX_ZOOM = 0.25, 8.0


def qimage_from_rgb(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, arr.strides[0], QImage.Format_RGB888)


class ImageView(QWidget):
    viewChanged = Signal(float, float, float)   # zoom, cx, cy (image-normalised)
    wipeChanged = Signal(float)
    markerClicked = Signal(float, float, int)   # image-normalised x, y; +1 keep (left) / -1 remove (right)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 120)
        self.setMouseTracking(True)
        self._arr: Optional[np.ndarray] = None
        self._img: Optional[QImage] = None
        self._wipe_arr: Optional[np.ndarray] = None
        self._wipe_img: Optional[QImage] = None
        self.message = ""
        self.zoom = 1.0
        self.cx = self.cy = 0.5
        self.wipe_on = False
        self.wipe_pos = 0.5
        self._drag = None          # ("pan", last_pos) | ("wipe", None)
        self._press = None         # (button, position) of the current click, to tell a click from a drag
        self.marker_mode = False
        self.markers: list[tuple[float, float, int]] = []
        self._overlay: Optional[QImage] = None
        self._overlay_buf = None

    # -- content -----------------------------------------------------------
    def set_image(self, arr: Optional[np.ndarray], message: str = "") -> None:
        self._arr = arr
        self._img = qimage_from_rgb(arr) if arr is not None else None
        self.message = message
        self.update()

    def set_wipe_image(self, arr: Optional[np.ndarray]) -> None:
        self._wipe_arr = arr
        self._wipe_img = qimage_from_rgb(arr) if arr is not None else None
        self.update()

    def set_wipe(self, on: bool) -> None:
        self.wipe_on = on
        self.update()

    # -- subject marker tool ---------------------------------------------------
    def set_marker_mode(self, on: bool) -> None:
        self.marker_mode = on
        self.setCursor(Qt.CrossCursor) if on else self.unsetCursor()
        self.update()

    def set_markers(self, markers) -> None:
        self.markers = list(markers)
        self.update()

    def set_overlay(self, rgba: Optional[np.ndarray]) -> None:
        """Semi-transparent subject tint (H x W x 4 uint8) drawn over the image, or None."""
        if rgba is None:
            self._overlay, self._overlay_buf = None, None
        else:
            self._overlay_buf = np.ascontiguousarray(rgba)
            h, w = self._overlay_buf.shape[:2]
            self._overlay = QImage(self._overlay_buf.data, w, h, self._overlay_buf.strides[0],
                                   QImage.Format_RGBA8888)
        self.update()

    # -- view state --------------------------------------------------------
    def set_view(self, zoom: float, cx: float, cy: float, emit: bool = False) -> None:
        self.zoom = min(max(zoom, MIN_ZOOM), MAX_ZOOM)
        self.cx, self.cy = cx, cy
        self.update()
        if emit:
            self.viewChanged.emit(self.zoom, self.cx, self.cy)

    def reset_view(self) -> None:
        self.set_view(1.0, 0.5, 0.5, emit=True)

    def _geometry(self):
        """-> (scale, top-left QPointF, image size) or None."""
        if self._img is None:
            return None
        iw, ih = self._img.width(), self._img.height()
        fit = min(self.width() / iw, self.height() / ih)
        s = fit * self.zoom
        tl = QPointF(self.width() / 2 - self.cx * iw * s, self.height() / 2 - self.cy * ih * s)
        return s, tl, (iw, ih)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_VIEW))
        g = self._geometry()
        if g is None:
            if self.message:
                p.setPen(QColor(T.TEXT_FAINT))
                p.drawText(self.rect(), Qt.AlignCenter, self.message)
            return
        s, tl, (iw, ih) = g
        target = QRectF(tl.x(), tl.y(), iw * s, ih * s)
        p.setRenderHint(QPainter.SmoothPixmapTransform, s < 2.0)
        if self.wipe_on and self._wipe_img is not None:
            wx = self.wipe_pos * self.width()
            p.save()
            p.setClipRect(QRectF(0, 0, wx, self.height()))
            p.drawImage(target, self._wipe_img)
            p.restore()
            p.save()
            p.setClipRect(QRectF(wx, 0, self.width() - wx, self.height()))
            p.drawImage(target, self._img)
            p.restore()
            p.setPen(QPen(QColor(T.ACCENT), 1))
            p.drawLine(int(wx), 0, int(wx), self.height())
            p.setBrush(QColor(T.ACCENT))
            p.setPen(Qt.NoPen)
            p.drawRect(int(wx) - 4, self.height() // 2 - 12, 8, 24)
        else:
            p.drawImage(target, self._img)
        if self._overlay is not None:
            p.drawImage(target, self._overlay)
        if self.markers:
            self._paint_markers(p, s, tl, iw, ih)

    def _paint_markers(self, p: QPainter, s: float, tl: QPointF, iw: int, ih: int) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        for nx, ny, sign in self.markers:
            c = QPointF(tl.x() + nx * iw * s, tl.y() + ny * ih * s)
            col = QColor(T.GREEN if sign > 0 else T.RED)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(col)
            p.drawEllipse(c, 8, 8)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(QPointF(c.x() - 4, c.y()), QPointF(c.x() + 4, c.y()))
            if sign > 0:
                p.drawLine(QPointF(c.x(), c.y() - 4), QPointF(c.x(), c.y() + 4))
        p.setRenderHint(QPainter.Antialiasing, False)

    # -- interaction -------------------------------------------------------
    def wheelEvent(self, e):
        g = self._geometry()
        if g is None:
            return
        dx = e.angleDelta().x()
        dy = e.angleDelta().y()
        s, tl, (iw, ih) = g
        if e.modifiers() & Qt.ShiftModifier:           # horizontal pan
            self.cx -= (dy or dx) / 8.0 / (iw * s) * 0.5
            self.set_view(self.zoom, self.cx, self.cy, emit=True)
            return
        pos = e.position()
        before = QPointF((pos.x() - tl.x()) / (iw * s), (pos.y() - tl.y()) / (ih * s))
        factor = 1.0015 ** dy
        new_zoom = min(max(self.zoom * factor, MIN_ZOOM), MAX_ZOOM)
        fit = min(self.width() / iw, self.height() / ih)
        ns = fit * new_zoom
        # keep the point under the cursor fixed
        self.cx = before.x() - (pos.x() - self.width() / 2) / (iw * ns)
        self.cy = before.y() - (pos.y() - self.height() / 2) / (ih * ns)
        self.set_view(new_zoom, self.cx, self.cy, emit=True)

    def mousePressEvent(self, e):
        self._press = (e.button(), e.position())
        if e.button() in (Qt.LeftButton, Qt.MiddleButton):
            if (self.wipe_on and e.button() == Qt.LeftButton
                    and abs(e.position().x() - self.wipe_pos * self.width()) < 10):
                self._drag = ("wipe", None)
            else:
                self._drag = ("pan", e.position())
                self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is None:
            if self.wipe_on and abs(e.position().x() - self.wipe_pos * self.width()) < 10:
                self.setCursor(Qt.SplitHCursor)
            elif self.marker_mode:
                self.setCursor(Qt.CrossCursor)
            else:
                self.unsetCursor()
            return
        kind, last = self._drag
        if kind == "wipe":
            self.wipe_pos = min(max(e.position().x() / max(self.width(), 1), 0.0), 1.0)
            self.update()
            self.wipeChanged.emit(self.wipe_pos)
            return
        g = self._geometry()
        if g is None:
            return
        s, _tl, (iw, ih) = g
        d = e.position() - last
        self._drag = ("pan", e.position())
        self.set_view(self.zoom, self.cx - d.x() / (iw * s), self.cy - d.y() / (ih * s), emit=True)

    def mouseReleaseEvent(self, e):
        press, self._press = self._press, None
        self._drag = None
        self.setCursor(Qt.CrossCursor) if self.marker_mode else self.unsetCursor()
        if (self.marker_mode and press is not None and press[0] in (Qt.LeftButton, Qt.RightButton)
                and (e.position() - press[1]).manhattanLength() < 5):        # a click, not a pan
            g = self._geometry()
            if g is None:
                return
            s, tl, (iw, ih) = g
            nx, ny = (e.position().x() - tl.x()) / (iw * s), (e.position().y() - tl.y()) / (ih * s)
            if 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0:
                self.markerClicked.emit(nx, ny, 1 if press[0] == Qt.LeftButton else -1)

    def mouseDoubleClickEvent(self, e):
        if self.marker_mode and e.button() in (Qt.LeftButton, Qt.RightButton):
            # two quick marker clicks arrive as press + double-click: count the second one as a click too
            self._press = (e.button(), e.position())
            return
        self.reset_view()


class ViewerPanel(QWidget):
    """Header rows + the two image views."""
    modeChanged = Signal(str)
    zoomChanged = Signal(float)
    markerClicked = Signal(float, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.media: Optional[ClipMedia] = None
        self.mode = "input"
        self.frame_idx = 0
        self._wipe = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(26)
        T.style_box(header, "vheader", "BG_BAR", bottom="LINE")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        left = QWidget()
        ll = QHBoxLayout(left)
        ll.setContentsMargins(8, 0, 8, 0)
        self.left_info = QLabel("")
        T.sty(self.left_info, lambda: f"color:{T.TEXT_DIM}; font-size:11px;")
        ll.addStretch(1)
        ll.addWidget(self.left_info)
        ll.addStretch(1)

        right = QWidget()
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 8, 0)
        rl.setSpacing(0)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tabs: dict[str, QPushButton] = {}
        for key, label in MODES:
            b = QPushButton(label)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setFixedHeight(22)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(H.ui_tip(f"tab_{key}"))
            b.clicked.connect(lambda _=False, k=key: self.set_mode(k))
            self.tab_group.addButton(b)
            self.tabs[key] = b
            rl.addWidget(b)
        self.tabs["input"].setChecked(True)
        rl.addStretch(1)
        self.right_info = QLabel("")
        T.sty(self.right_info, lambda: f"color:{T.TEXT_DIM}; font-size:11px;")
        rl.addWidget(self.right_info)

        hl.addWidget(left, 1)
        hl.addWidget(right, 1)
        lay.addWidget(header)

        views = QWidget()
        vl = QHBoxLayout(views)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(1)
        self.left_view = ImageView()
        self.right_view = ImageView()
        vl.addWidget(self.left_view, 1)
        vl.addWidget(self.right_view, 1)
        T.style_box(views, "vviews", "LINE_MID")
        lay.addWidget(views, 1)

        self.left_view.markerClicked.connect(self.markerClicked)
        for a, b in ((self.left_view, self.right_view), (self.right_view, self.left_view)):
            a.viewChanged.connect(lambda z, x, y, other=b: (other.set_view(z, x, y), self._zoom(z)))
        self._refresh_tabs()

    # -- external API ------------------------------------------------------
    def set_media(self, media: Optional[ClipMedia], info: str = "", short: str = "") -> None:
        self.media = media
        self.frame_idx = 0
        self.set_info(info, short)
        self._refresh_tabs()
        if self.media is None or not self.media.available(self.mode):
            if self.media is not None and self.media.has_outputs():
                self.mode = next(m for m in ("checker", "alpha", "fg", "cutout") if self.media.available(m))
            else:
                self.mode = "input"
            self.tabs[self.mode].setChecked(True)
        self.left_view.reset_view()
        self.refresh()

    def set_info(self, info: str, short: str = "") -> None:
        self.left_info.setText(info)
        self.right_info.setText(short or info)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.tabs[mode].setChecked(True)
        self.refresh()
        self.modeChanged.emit(mode)

    def set_frame(self, i: int) -> None:
        self.frame_idx = i
        self.refresh()

    def set_wipe(self, on: bool) -> None:
        self._wipe = on
        self.right_view.set_wipe(on)
        self.refresh()

    def toggle_wipe(self) -> None:
        self.set_wipe(not self._wipe)

    def reset_view(self) -> None:
        self.left_view.reset_view()

    def refresh_tabs(self) -> None:
        self._refresh_tabs()

    # -- subject marker tool (works on the INPUT view) ---------------------
    def set_marker_mode(self, on: bool) -> None:
        self.left_view.set_marker_mode(on)

    def set_markers(self, markers) -> None:
        self.left_view.set_markers(markers)

    def set_overlay(self, rgba) -> None:
        self.left_view.set_overlay(rgba)

    # -- internals ---------------------------------------------------------
    def _zoom(self, z: float) -> None:
        self.zoomChanged.emit(z)

    def _refresh_tabs(self) -> None:
        for key, b in self.tabs.items():
            ok = self.media is not None and (key == "input" or self.media.available(key))
            b.setEnabled(ok)

    def refresh(self) -> None:
        m = self.media
        if m is None:
            self.left_view.set_image(None, "")
            self.right_view.set_image(None, "")
            return
        arr, note = m.frame("input", self.frame_idx)
        self.left_view.set_image(arr, note)
        if self.mode == "input":
            right, rnote = arr, note
        else:
            right, rnote = m.frame(self.mode, self.frame_idx)
        self.right_view.set_image(right, rnote)
        self.right_view.set_wipe_image(arr if self._wipe else None)
