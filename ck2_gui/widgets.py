"""Chrome around the viewers: brand bar, queue, scrubber, clip tray, status."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from html import escape

from . import help_text as H
from . import theme as T

# 5x7 pixel glyphs for the wordmark (the Corridor Key 1 GUI uses a chunky pixel logo).
_GLYPHS = {
    "C": [".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "I": [".XXX.", "..X..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
    "K": ["X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "S": [".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."],
}


class Wordmark(QWidget):
    def __init__(self, cell: int = 2, parent=None):
        super().__init__(parent)
        self.cell = cell
        self.text = "CORRIDORKEY"
        w = len(self.text) * 6 * cell
        self.setFixedSize(w, 7 * cell)

    def paintEvent(self, _e):
        p = QPainter(self)
        c = self.cell
        x0 = 0
        for i, ch in enumerate(self.text):
            p.setBrush(QColor(T.ACCENT if i < 8 else T.GREEN))      # CORRIDOR yellow, KEY green
            p.setPen(Qt.NoPen)
            for r, row in enumerate(_GLYPHS[ch]):
                for col, v in enumerate(row):
                    if v == "X":
                        p.drawRect(x0 + col * c, r * c, c, c)
            x0 += 6 * c


class VramMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 8)
        self.fraction = 0.0

    def set_fraction(self, f: float) -> None:
        self.fraction = min(max(f, 0.0), 1.0)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_FIELD))
        w = int(self.width() * self.fraction)
        if w > 0:
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0.0, QColor(T.GREEN))
            g.setColorAt(0.65, QColor(T.ACCENT))
            g.setColorAt(1.0, QColor(T.RED))
            p.fillRect(0, 0, w, self.height(), g)
        p.setPen(QPen(QColor(T.LINE_FIELD), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)


class BrandBar(QWidget):
    settingsClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        T.style_box(self, "brandbar", "BG_BRAND", bottom="LINE")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 10, 0)
        lay.setSpacing(8)
        mark = Wordmark(2)
        mark.setToolTip(H.ui_tip("brand"))
        lay.addWidget(mark)
        tag = QLabel("2.0")
        T.sty(tag, lambda: f"color:{T.ACCENT_DARK}; font-size:10px; font-weight:bold; letter-spacing:1px;")
        lay.addWidget(tag)
        # The window shares the model's name, so say plainly that it is an unofficial front-end (licence section 4).
        credit = QLabel("unofficial GUI \u00b7 keying model by Corridor Digital")
        T.sty(credit, lambda: f"color:{T.TEXT_FAINT}; font-size:10px; letter-spacing:1px;")
        credit.setToolTip(H.ui_tip("brand"))
        lay.addWidget(credit)
        lay.addStretch(1)
        self.gpu = QLabel("NO GPU DETECTED")
        T.sty(self.gpu, lambda: f"color:{T.TEXT_DIM}; font-size:10px; letter-spacing:1px;")
        self.gpu.setToolTip(H.ui_tip("gpu"))
        vram = QLabel("VRAM")
        T.sty(vram, lambda: f"color:{T.TEXT_FAINT}; font-size:10px; letter-spacing:1px;")
        vram.setToolTip(H.ui_tip("vram"))
        self.meter = VramMeter()
        self.meter.setToolTip(H.ui_tip("vram"))
        self.mem = QLabel("")
        T.sty(self.mem, lambda: f"color:{T.TEXT_DIM}; font-size:10px;")
        self.settings = QPushButton("\u2699  SETTINGS")
        self.settings.setObjectName("ghost")
        self.settings.setToolTip(H.ui_tip("settings"))
        self.settings.clicked.connect(self.settingsClicked)
        for w in (self.gpu, vram, self.meter, self.mem, self.settings):
            lay.addWidget(w)

    def set_gpu(self, info: Optional[tuple]) -> None:
        if not info:
            self.gpu.setText("NO NVIDIA GPU / nvidia-smi")
            self.meter.set_fraction(0)
            self.mem.setText("")
            return
        name, used, total = info
        name = name.replace("NVIDIA ", "").replace("GeForce ", "").upper()
        self.gpu.setText(name)
        self.meter.set_fraction(used / total if total else 0)
        self.mem.setText(f"{used:.1f}/{total:.1f}GB")


# --------------------------------------------------------------------------
class QueuePanel(QWidget):
    removeRequested = Signal(str)
    clearRequested = Signal()
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.panel = QWidget()
        self.panel.setFixedWidth(168)
        T.style_box(self.panel, "queuepanel", "BG_BAR", right="LINE")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(8, 8, 8, 8)
        pl.setSpacing(6)
        head = QHBoxLayout()
        self.title = QLabel("QUEUE (0)")
        T.sty(self.title, lambda: f"color:{T.TEXT}; font-weight:bold; font-size:11px; letter-spacing:1px; border:none;")
        self.title.setToolTip(H.ui_tip("queue"))
        clear = QPushButton("Clear")
        clear.setObjectName("ghost")
        clear.clicked.connect(self.clearRequested)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(clear)
        pl.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(0, 0, 0, 0)
        self.body_l.setSpacing(4)
        self.body_l.addStretch(1)
        self.scroll.setWidget(self.body)
        pl.addWidget(self.scroll, 1)

        self.rail = QPushButton()
        self.rail.setFixedWidth(14)
        self.rail.setCursor(Qt.PointingHandCursor)
        self.rail.setToolTip("Toggle queue (Q)")
        T.sty(self.rail, lambda: f"QPushButton{{background:{T.BG_BAR}; border:none; border-right:1px solid {T.LINE};"
                                 f"padding:0;}} QPushButton:hover{{background:{T.BG_BTN};}}")
        self.rail.clicked.connect(lambda: self.set_open(not self._open))
        self.rail.setText("")
        lay.addWidget(self.panel)
        lay.addWidget(self.rail)

    def paintEvent(self, e):
        super().paintEvent(e)

    def set_open(self, open_: bool) -> None:
        self._open = open_
        self.panel.setVisible(open_)
        self.toggled.emit(open_)

    def is_open(self) -> bool:
        return self._open

    def refresh(self, jobs: list[dict]) -> None:
        self.title.setText(f"QUEUE ({len(jobs)})")
        while self.body_l.count() > 1:
            w = self.body_l.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for j in jobs:
            self.body_l.insertWidget(self.body_l.count() - 1, self._row(j))

    def _row(self, j: dict) -> QWidget:
        w = QFrame()
        w.setObjectName("qrow")
        T.sty(w, lambda: f"QFrame#qrow{{background:{T.BG_ROW}; border:1px solid {T.LINE};}}")
        l = QHBoxLayout(w)
        l.setContentsMargins(6, 4, 4, 4)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(j["title"])
        T.sty(t, lambda: f"color:{T.TEXT_DIM}; font-size:9px; font-weight:bold; border:none;")
        n = QLabel(QFontMetrics(self.font()).elidedText(j["name"], Qt.ElideMiddle, 120))
        T.sty(n, lambda: f"color:{T.TEXT}; font-size:10px; border:none;")
        st = QLabel(j["status"])
        T.sty(st, lambda: f"color:{T.STATUS_COLORS.get(j['status'], T.TEXT_DIM)}; font-size:9px;"
                          f"font-weight:bold; border:none;")
        for x in (t, n, st):
            col.addWidget(x)
        l.addLayout(col, 1)
        if j["status"] != "RUNNING":
            x = QPushButton("\u2715")
            x.setFixedSize(18, 18)
            T.sty(x, lambda: f"QPushButton{{border:none; background:transparent; color:{T.TEXT_DIM}; padding:0;}}"
                             f"QPushButton:hover{{color:{T.RED};}}")
            x.setToolTip("Remove this waiting job")
            x.clicked.connect(lambda _=False, i=j["id"]: self.removeRequested.emit(i))
            l.addWidget(x, 0, Qt.AlignTop)
        return w


# --------------------------------------------------------------------------
class ScrubBar(QWidget):
    frameChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(H.ui_tip("scrub"))
        self.count = 0
        self.frame = 0
        self.plan: Optional[tuple[int, int]] = None      # frames that will be processed
        self.done: Optional[tuple[int, int]] = None      # frames with outputs
        self.hint = "none"                               # none | first | video
        self.margin = 6

    def set_state(self, count: int, frame: int, plan=None, done=None, hint="none") -> None:
        self.count, self.frame, self.plan, self.done, self.hint = count, frame, plan, done, hint
        self.update()

    def _x(self, f: float) -> float:
        span = max(self.count - 1, 1)
        return self.margin + (self.width() - 2 * self.margin) * (f / span)

    def paintEvent(self, _e):
        p = QPainter(self)
        w = self.width()
        top, bot = 8, 19
        p.setPen(QPen(QColor(T.SCRUB_A), 2))
        p.drawLine(self.margin, top, w - self.margin, top)
        p.setPen(QPen(QColor(T.SCRUB_B), 2))
        p.drawLine(self.margin, bot, w - self.margin, bot)
        if self.count <= 0:
            return
        if self.done:                                    # frames that have outputs
            a, b = self.done
            p.setPen(QPen(QColor(T.ACCENT), 3))
            p.drawLine(int(self._x(a)), top, int(self._x(max(b - 1, a))), top)
        if self.hint == "video":                         # hint coverage
            p.setPen(QPen(QColor(T.MARK), 2))
            p.drawLine(self.margin, bot, w - self.margin, bot)
        elif self.hint == "first":
            p.setPen(QPen(QColor(T.MARK), 2))
            p.drawLine(int(self._x(0)), bot - 3, int(self._x(0)), bot + 3)
        if self.plan and self.plan[1] < self.count:      # partial range bracket
            a, b = self.plan
            x0, x1 = int(self._x(a)), int(self._x(max(b - 1, a)))
            p.setPen(QPen(QColor(T.ACCENT), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRect(x0, 3, max(x1 - x0, 1), 21)
        x = self._x(self.frame)                          # playhead
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.GREEN))
        p.drawRect(QRectF(x - 4, bot - 4, 8, 8))

    def _seek(self, px: float) -> None:
        if self.count <= 0:
            return
        span = max(self.width() - 2 * self.margin, 1)
        f = round((px - self.margin) / span * (self.count - 1))
        f = min(max(int(f), 0), self.count - 1)
        if f != self.frame:
            self.frame = f
            self.update()
            self.frameChanged.emit(f)

    def mousePressEvent(self, e):
        self._seek(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._seek(e.position().x())


class Scrubber(QWidget):
    frameChanged = Signal(int)
    playToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        T.style_box(self, "scrubber", "BG_ROOT", top="LINE")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 8, 0)
        lay.setSpacing(2)
        self.bar = ScrubBar()
        self.bar.frameChanged.connect(self.frameChanged)
        self.label = QLabel("")
        T.sty(self.label, lambda: f"color:{T.TEXT_DIM}; font-size:11px; border:none;")
        self.label.setMinimumWidth(92)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.zoom = QLabel("100%")
        T.sty(self.zoom, lambda: f"color:{T.TEXT_DIM}; font-size:11px; border:none;")
        self.zoom.setToolTip(H.ui_tip("zoom"))
        self.zoom.setMinimumWidth(40)
        self.zoom.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        def btn(txt, tip, slot):
            b = QPushButton(txt)
            b.setObjectName("transport")
            b.setToolTip(tip)
            b.setFixedWidth(26)
            b.clicked.connect(slot)
            return b

        self.first = btn("\u23ee", "First frame (Home)", lambda: self._go(0))
        self.prev = btn("\u25c0", "Step back (\u2190)", lambda: self._go(self.bar.frame - 1))
        self.play = btn("\u25b6", "Play / pause (Space)", self._toggle)
        self.next = btn("\u25b6\u25b6", "Step forward (\u2192)", lambda: self._go(self.bar.frame + 1))
        self.last = btn("\u23ed", "Last frame (End)", lambda: self._go(self.bar.count - 1))
        self.next.setFixedWidth(34)
        for w in (self.first, self.prev, self.play, self.next, self.last):
            lay.addWidget(w)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.label)
        lay.addWidget(self.zoom)
        self.playing = False

    def _toggle(self) -> None:
        self.set_playing(not self.playing)
        self.playToggled.emit(self.playing)

    def set_playing(self, on: bool) -> None:
        self.playing = on
        self.play.setText("\u275a\u275a" if on else "\u25b6")

    def _go(self, f: int) -> None:
        if self.bar.count <= 0:
            return
        f = min(max(f, 0), self.bar.count - 1)
        self.set_frame(f)
        self.frameChanged.emit(f)

    def go(self, f: int) -> None:
        self._go(f)

    def set_frame(self, f: int) -> None:
        self.bar.frame = f
        self.bar.update()
        self._label()

    def set_state(self, count: int, frame: int, plan=None, done=None, hint="none") -> None:
        self.bar.set_state(count, frame, plan, done, hint)
        self._label()

    def _label(self) -> None:
        c = self.bar.count
        self.label.setText(f"{self.bar.frame + 1} / {c}" if c else "")

    def set_zoom(self, z: float) -> None:
        self.zoom.setText(f"{round(z * 100)}%")


# --------------------------------------------------------------------------
class ClipCard(QWidget):
    clicked = Signal(str, object)
    doubleClicked = Signal(str)
    context = Signal(str, object)

    W, H, TH = 112, 88, 58

    def __init__(self, cid: str, name: str, frames: int, status: str, pix: Optional[QPixmap],
                 selected: bool, parent=None):
        super().__init__(parent)
        self.cid, self.name, self.frames, self.status = cid, name, frames, status
        self.pix, self.selected = pix, selected
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(H.ui_tip("card").replace("<b>Clip</b>", f"<b>{escape(name)}</b>", 1))

    def paintEvent(self, _e):
        p = QPainter(self)
        r = self.rect().adjusted(0, 0, -1, -1)
        p.fillRect(r, QColor(T.BG_CARD))
        thumb = QRectF(2, 2, self.W - 4, self.TH)
        p.fillRect(thumb, QColor(T.BG_DEEP))
        if self.pix is not None and not self.pix.isNull():
            s = self.pix.scaled(int(thumb.width()), int(thumb.height()),
                                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(thumb.x() + (thumb.width() - s.width()) / 2),
                         int(thumb.y() + (thumb.height() - s.height()) / 2), s)
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        col = QColor(T.STATUS_COLORS.get(self.status, T.TEXT_DIM))
        badge = self.status
        bw = QFontMetrics(f).horizontalAdvance(badge) + 8
        br = QRectF(self.W - bw - 3, 3, bw, 14)
        bgc = QColor(T.BG_ROOT)
        bgc.setAlpha(205)
        p.fillRect(br, bgc)
        p.setPen(col)
        p.drawText(br, Qt.AlignCenter, badge)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(T.TEXT_BRIGHT))
        nm = QFontMetrics(f).elidedText(self.name, Qt.ElideRight, self.W - 8)
        p.drawText(QRectF(4, self.TH + 4, self.W - 8, 14), Qt.AlignLeft | Qt.AlignVCenter, nm)
        f.setBold(False)
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(T.TEXT_DIM))
        p.drawText(QRectF(4, self.TH + 17, self.W - 8, 12), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{self.frames} frames")
        p.setPen(QPen(QColor(T.ACCENT if self.selected else T.LINE), 2 if self.selected else 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.cid, e.modifiers())
        elif e.button() == Qt.RightButton:
            self.context.emit(self.cid, e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.cid)


class _CardStrip(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(ClipCard.H + 12)
        self.inner = QWidget()
        self.lay = QHBoxLayout(self.inner)
        self.lay.setContentsMargins(0, 2, 0, 2)
        self.lay.setSpacing(6)
        self.lay.addStretch(1)
        self.setWidget(self.inner)

    def set_cards(self, cards: list[QWidget]) -> None:
        while self.lay.count() > 1:
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for c in cards:
            self.lay.insertWidget(self.lay.count() - 1, c)


class Tray(QWidget):
    selected = Signal(str, object)
    opened = Signal(str)
    context = Signal(str, object)
    addRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        T.style_box(self, "tray", "BG_ROOT")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 2)
        lay.setSpacing(6)

        def head(title: str, add: bool):
            h = QHBoxLayout()
            lbl = QLabel(title)
            T.sty(lbl, lambda: f"color:{T.TEXT_DIM}; font-size:10px; font-weight:bold; letter-spacing:1px;")
            h.addWidget(lbl)
            h.addStretch(1)
            if add:
                b = QPushButton("+ ADD")
                b.setObjectName("ghost")
                b.clicked.connect(self.addRequested)
                h.addWidget(b)
            return h, lbl

        left = QVBoxLayout()
        lh, self.in_label = head("INPUT (0)", True)
        self.in_label.setToolTip(H.ui_tip("tray_in"))
        left.addLayout(lh)
        self.in_strip = _CardStrip()
        left.addWidget(self.in_strip)
        right = QVBoxLayout()
        rh, self.out_label = head("EXPORTS (0)", False)
        self.out_label.setToolTip(H.ui_tip("tray_out"))
        right.addLayout(rh)
        self.out_strip = _CardStrip()
        right.addWidget(self.out_strip)
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setObjectName("traysep")
        T.sty(sep, lambda: f"QFrame#traysep{{background:{T.LINE_MID};}}")
        lay.addLayout(left, 1)
        lay.addWidget(sep)
        lay.addLayout(right, 1)
        self.setFixedHeight(ClipCard.H + 36)

    def refresh(self, clips, thumbs: dict, selected_ids: set) -> None:
        def mk(c):
            card = ClipCard(c.id, c.name, c.frames, c.status, thumbs.get(c.id), c.id in selected_ids)
            card.clicked.connect(self.selected)
            card.doubleClicked.connect(self.opened)
            card.context.connect(self.context)
            return card
        self.in_label.setText(f"INPUT ({len(clips)})")
        self.in_strip.set_cards([mk(c) for c in clips])
        done = [c for c in clips if c.status == "COMPLETE"]
        self.out_label.setText(f"EXPORTS ({len(done)})")
        self.out_strip.set_cards([mk(c) for c in done])


# --------------------------------------------------------------------------
class ProgressStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 6)
        self.setToolTip(H.ui_tip("progress"))
        self.fraction = 0.0

    def set_fraction(self, f: float) -> None:
        self.fraction = min(max(f, 0.0), 1.0)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_FIELD))
        p.fillRect(0, 0, int(self.width() * self.fraction), self.height(), QColor(T.ACCENT))


class StatusBar(QWidget):
    runClicked = Signal()
    runAllClicked = Signal()
    stopClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        T.style_box(self, "statusbar", "BG_BAR", top="LINE")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)
        self.progress = ProgressStrip()
        self.text = QLabel("Ready. Drop a clip, frame sequence or folder to begin.")
        T.sty(self.text, lambda: f"color:{T.TEXT_DIM}; font-size:11px;")
        self.text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.eta = QLabel("")
        T.sty(self.eta, lambda: f"color:{T.TEXT_DIM}; font-size:11px;")
        self.run = QPushButton("RUN INFERENCE")
        self.run.setObjectName("primary")
        self.run_all = QPushButton("RUN ALL")
        self.run_all.setObjectName("secondary")
        self.run.setToolTip(H.ui_tip("run"))
        self.run_all.setToolTip(H.ui_tip("run_all"))
        self.run.clicked.connect(self._run)
        self.run_all.clicked.connect(self.runAllClicked)
        lay.addWidget(self.progress)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.eta)
        lay.addWidget(self.run_all)
        lay.addWidget(self.run)
        self.running = False

    def _run(self) -> None:
        (self.stopClicked if self.running else self.runClicked).emit()

    def set_running(self, running: bool) -> None:
        self.running = running
        self.run.setText("STOP" if running else "RUN INFERENCE")
        self.run.setToolTip(H.ui_tip("stop" if running else "run"))
        self.run.setObjectName("stop" if running else "primary")
        self.run.style().unpolish(self.run)
        self.run.style().polish(self.run)
        self.run_all.setEnabled(not running)

    def set_run_label(self, text: str) -> None:
        if not self.running:
            self.run.setText(text)

    def message(self, text: str) -> None:
        self.text.setText(text)
        self.text.setToolTip(text)
