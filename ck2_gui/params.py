"""Right-hand parameter panel. Edits the selected clip's Settings in place.

Every section header and every control carries a plain-language tooltip (see help_text.py). Tooltips appear next to
the mouse only; for value controls the tooltip is rebuilt the moment it is about to show, so its "Right now:" sentence
always describes the current value.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from . import help_text as H
from . import theme as T
from .model import HANN_PRESETS, OUTPUT_KEYS, OUTPUT_LABELS, Settings

PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
PIX_FMTS = ["yuv444p10le", "yuv444p", "yuv422p10le", "yuv420p10le", "yuv420p"]
BITRATE_RE = QRegularExpression(r"^\d{1,6}(\.\d{1,2})?[kKmM]?$")

MARKER_GROW_RANGE = (-30, 30)      # tenths of a percent of the frame height
MARKER_SOFT_RANGE = (0, 40)


class ResetSlider(QSlider):
    """Middle-click resets to the default (same convenience as the CK1 GUI)."""

    def __init__(self, default: int, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.default = default

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.setValue(self.default)
            return
        super().mousePressEvent(e)


class Section(QWidget):
    def __init__(self, title: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.head = QPushButton(("▸  " if collapsed else "▾  ") + title)
        self.head.setCursor(Qt.PointingHandCursor)
        T.sty(self.head, lambda: (
            f"QPushButton{{background:{T.c('BG_PANEL')}; border:none; border-top:1px solid {T.c('LINE')};"
            f"color:{T.c('TEXT_DIM')}; text-align:left; padding:7px 8px; font-size:10px; font-weight:bold;"
            f"letter-spacing:1.5px;}} QPushButton:hover{{color:{T.c('ACCENT_FG')};}}"))
        self.title = title
        self.body = QWidget()
        self.form = QVBoxLayout(self.body)
        self.form.setContentsMargins(10, 4, 10, 10)
        self.form.setSpacing(7)
        self.body.setVisible(not collapsed)
        self.head.clicked.connect(self._toggle)
        outer.addWidget(self.head)
        outer.addWidget(self.body)

    def _toggle(self) -> None:
        vis = not self.body.isVisible()
        self.body.setVisible(vis)
        self.head.setText(("▾  " if vis else "▸  ") + self.title)

    def set_open(self, vis: bool) -> None:
        if vis != self.body.isVisible():
            self._toggle()


class _Hover(QObject):
    """Just before a registered widget's tooltip is shown, rebuild it so "Right now:" is up to date."""

    def __init__(self, panel: "ParamPanel"):
        super().__init__(panel)
        self.panel = panel

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.ToolTip:
            self.panel._fresh_tip(obj)
        return False


def _ghost(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("ghost")
    b.setFixedHeight(26)
    if tip:
        b.setToolTip(tip)
    return b


class ParamPanel(QWidget):
    edited = Signal()
    applyAll = Signal()
    markerModeChanged = Signal(bool)     # "PLACE MARKERS" toggled by the user
    markerUndo = Signal()
    markerClear = Signal()
    markerGoto = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.s: Optional[Settings] = None
        self.kind = "video"
        self._loading = False
        self._prev_mode = "none"
        self._keys: dict[QObject, str] = {}        # widget -> help key
        self._sections: list[Section] = []
        self._hover = _Hover(self)
        self.setFixedWidth(300)
        T.style_box(self, "params", "BG_PANEL", left="LINE")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        self.col = QVBoxLayout(host)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(0)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        self._build_hint()
        self._build_inference()
        self._build_memory()
        self._build_range()
        self._build_output()
        self._build_encoding()
        self.col.addStretch(1)

        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(10, 8, 10, 8)
        self.apply_all = QPushButton("APPLY TO ALL CLIPS")
        self.apply_all.clicked.connect(self.applyAll)
        fl.addWidget(self.apply_all)
        T.style_box(foot, "paramfoot", "BG_PANEL", top="LINE")
        outer.addWidget(foot)
        self._help("apply_all", self.apply_all, ui=True)

        self.set_settings(None, "video")
        self.refresh_help()

    # -- help plumbing ---------------------------------------------------------
    def _help(self, key: str, *widgets: QWidget, ui: bool = False) -> None:
        for w in widgets:
            self._keys[w] = ("ui:" + key) if ui else key
            w.installEventFilter(self._hover)

    def _tip_for(self, key: str) -> str:
        if key.startswith("ui:"):
            return H.ui_tip(key[3:])
        return H.control_tip(key, self._now(key))

    def refresh_help(self) -> None:
        """(Re)apply tooltips - called at start-up and whenever hover help is switched on or off."""
        on = H.ENABLED
        for w, key in self._keys.items():
            w.setToolTip(self._tip_for(key) if on else "")
        for sec in self._sections:
            sec.head.setToolTip(H.section_tip(sec.title) if on else "")
        for i in range(self.hint_mode.count()):
            d = str(self.hint_mode.itemData(i) or "")
            self.hint_mode.setItemData(i, (H.dynamic("hint_mode", d) if on else ""), Qt.ToolTipRole)

    def _fresh_tip(self, obj) -> None:
        """Called by the ToolTip event, i.e. right before Qt reads the tooltip text."""
        key = self._keys.get(obj)
        if not H.ENABLED or key is None:
            return
        tip = self._tip_for(key)
        if tip and tip != obj.toolTip():
            obj.setToolTip(tip)

    def _now(self, key: str) -> str:
        if key.startswith("ui:"):
            return ""
        m = {
            "hint_mode": lambda: self.hint_mode.currentData(),
            "hint_quality": lambda: self.hq.value() / 100,
            "carry_quality": lambda: self.cq.value() / 100,
            "marker_grow": lambda: self.mk_grow.value(),
            "marker_soft": lambda: self.mk_soft.value(),
            "despill": lambda: self.despill.value() / 100,
            "model_scale": lambda: self.scale.value(),
            "profile": lambda: bool(self.profile.currentData()),
            "hann": lambda: (self.chunk.value(), self.stride.value()),
            "limit": lambda: self.limit.value(),
            "fmt": lambda: self.fmt.currentData(),
            "crf": lambda: self.crf.value(),
            "rate_mode": lambda: self.rate_mode.currentData(),
            "bitrate": lambda: self.bitrate.text().strip(),
            "pix_fmt": lambda: self.pix.currentText().strip(),
            "threads": lambda: self.threads.value(),
        }.get(key)
        return H.dynamic(key, m()) if m else ""

    # -- builders -----------------------------------------------------------
    def _section(self, title: str, collapsed: bool = False) -> Section:
        sec = Section(title, collapsed)
        self._sections.append(sec)
        self.col.addWidget(sec)
        return sec

    def _row(self, label: str, widget: QWidget, key: str = "") -> tuple[QHBoxLayout, QLabel]:
        l = QHBoxLayout()
        l.setSpacing(8)
        lab = QLabel(label)
        l.addWidget(lab)
        l.addStretch(1)
        l.addWidget(widget)
        if key:
            self._help(key, lab, widget)
        return l, lab

    def _slider(self, default: int, lo=0, hi=100):
        sl = ResetSlider(default)
        sl.setRange(lo, hi)
        sl.setValue(default)
        return sl

    def _path_line(self, line: QLineEdit, key: str, with_file: bool = False):
        bd = _ghost("DIR" if with_file else "...")
        hl = QHBoxLayout()
        hl.setSpacing(4)
        hl.addWidget(line, 1)
        btns = [bd]
        if with_file:
            bf = _ghost("FILE")
            hl.addWidget(bf)
            btns.insert(0, bf)
        hl.addWidget(bd)
        bd.clicked.connect(lambda: self._pick(line, "dir"))
        if with_file:
            btns[0].clicked.connect(lambda: self._pick(line, "file"))
        self._help(key, line)
        return hl, btns

    def _build_hint(self) -> None:
        sec = self._section("HINT")
        self.hint_mode = QComboBox()
        self.hint_mode.addItem("No Hint", "none")
        self.hint_mode.addItem("Subject Marker (click it)", "marker")
        self.hint_mode.addItem("First-Frame Hint", "first")
        self.hint_mode.addItem("Full Hint Video", "video")
        self._help("hint_mode", self.hint_mode)
        sec.form.addWidget(self.hint_mode)

        # --- file / folder hint
        self.path_row = QWidget()
        pr = QVBoxLayout(self.path_row)
        pr.setContentsMargins(0, 0, 0, 0)
        self.hint_path = QLineEdit()
        self.hint_path.setPlaceholderText("Hint image / video / frame folder")
        hl, (self.hint_file, self.hint_dir) = self._path_line(self.hint_path, "hint_path", with_file=True)
        pr.addLayout(hl)
        sec.form.addWidget(self.path_row)

        # --- subject marker tools
        self.marker_box = QWidget()
        mb = QVBoxLayout(self.marker_box)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.setSpacing(6)
        self.mk_place = QPushButton("PLACE MARKERS")
        self.mk_place.setCheckable(True)
        mb.addWidget(self.mk_place)
        self.mk_howto = QLabel("Left-click = keep this.  Right-click = remove this.")
        self.mk_howto.setWordWrap(True)
        T.sty(self.mk_howto, lambda: f"QLabel{{color:{T.c('TEXT_DIM')}; font-size:11px;}}")
        mb.addWidget(self.mk_howto)
        br = QHBoxLayout()
        br.setSpacing(4)
        self.mk_undo = _ghost("UNDO")
        self.mk_clear = _ghost("CLEAR")
        self.mk_goto = _ghost("GO TO FRAME")
        for b in (self.mk_undo, self.mk_clear, self.mk_goto):
            br.addWidget(b)
        mb.addLayout(br)
        self.mk_status = QLabel("No markers yet.")
        self.mk_status.setWordWrap(True)
        self._mk_ok = True
        T.sty(self.mk_status, self._status_css)
        mb.addWidget(self.mk_status)
        self.mk_grow = self._slider(0, *MARKER_GROW_RANGE)
        self.mk_grow_lab = QLabel()
        self.mk_soft = self._slider(8, *MARKER_SOFT_RANGE)
        self.mk_soft_lab = QLabel()
        for lab, sl in ((self.mk_grow_lab, self.mk_grow), (self.mk_soft_lab, self.mk_soft)):
            mb.addWidget(lab)
            mb.addWidget(sl)
        self._help("marker", self.mk_place, self.mk_howto, self.mk_status)
        self._help("marker_grow", self.mk_grow_lab, self.mk_grow)
        self._help("marker_soft", self.mk_soft_lab, self.mk_soft)
        for b, tip in ((self.mk_undo, "Remove the last marker you placed."),
                       (self.mk_clear, "Remove all markers."),
                       (self.mk_goto, "Jump the viewer to the frame the markers belong on - the first frame that "
                                      "will be processed.")):
            b.setToolTip(tip)
        sec.form.addWidget(self.marker_box)

        # --- trust sliders
        self.hq = self._slider(95)
        self.hq_lab = QLabel()
        sec.form.addWidget(self.hq_lab)
        sec.form.addWidget(self.hq)
        self._help("hint_quality", self.hq_lab, self.hq)
        self.cq = self._slider(95)
        self.cq_lab = QLabel()
        sec.form.addWidget(self.cq_lab)
        sec.form.addWidget(self.cq)
        self._help("carry_quality", self.cq_lab, self.cq)
        self.no_carry = QCheckBox("Hint is authoritative (no carry)")
        self._help("no_carry", self.no_carry)
        sec.form.addWidget(self.no_carry)

        self.hint_mode.currentIndexChanged.connect(self._mode_changed)
        self.hint_path.editingFinished.connect(self._commit)
        self.hq.valueChanged.connect(self._commit)
        self.cq.valueChanged.connect(self._commit)
        self.no_carry.toggled.connect(self._commit)
        self.mk_grow.valueChanged.connect(self._commit)
        self.mk_soft.valueChanged.connect(self._commit)
        self.mk_place.toggled.connect(lambda on: None if self._loading else self.markerModeChanged.emit(bool(on)))
        self.mk_undo.clicked.connect(self.markerUndo)
        self.mk_clear.clicked.connect(self.markerClear)
        self.mk_goto.clicked.connect(self.markerGoto)

    def _status_css(self) -> str:
        col = T.c("TEXT_DIM") if self._mk_ok else T.c("ORANGE")
        return f"QLabel{{color:{col}; font-size:11px;}}"

    def _build_inference(self) -> None:
        sec = self._section("INFERENCE")
        self.space = QComboBox()
        self.space.addItem("sRGB (display-coded)", False)
        self.space.addItem("Linear (scene-linear)", True)
        r, self.space_lab = self._row("Input Color Space", self.space, "space")
        sec.form.addLayout(r)
        self.despill = self._slider(50)
        self.despill_lab = QLabel()
        sec.form.addWidget(self.despill_lab)
        sec.form.addWidget(self.despill)
        self._help("despill", self.despill_lab, self.despill)
        self.cutout_linear = QCheckBox("Cutout as straight linear RGB")
        self._help("cutout_linear", self.cutout_linear)
        sec.form.addWidget(self.cutout_linear)
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.1, 2.0)
        self.scale.setSingleStep(0.05)
        self.scale.setDecimals(2)
        self.scale.setFixedWidth(80)
        r, _ = self._row("Model Scale", self.scale, "model_scale")
        sec.form.addLayout(r)
        self.space.currentIndexChanged.connect(self._commit)
        self.despill.valueChanged.connect(self._commit)
        self.cutout_linear.toggled.connect(self._commit)
        self.scale.valueChanged.connect(self._commit)

    def _build_memory(self) -> None:
        sec = self._section("GPU MEMORY")
        self.profile = QComboBox()
        self.profile.addItem("Auto (recommended)", True)
        self.profile.addItem("Manual", False)
        self._help("profile", self.profile)
        sec.form.addWidget(self.profile)
        self.manual = QWidget()
        ml = QVBoxLayout(self.manual)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(7)
        self.hann = QComboBox()
        for label, c, s in HANN_PRESETS:
            self.hann.addItem(label, (c, s))
        self.hann.addItem("Custom", None)
        self.hann_lab = QLabel("Hann Window (time awareness)")
        ml.addWidget(self.hann_lab)
        ml.addWidget(self.hann)
        self._help("hann", self.hann_lab, self.hann)
        self.chunk = QSpinBox()
        self.chunk.setRange(1, 200)
        self.stride = QSpinBox()
        self.stride.setRange(1, 200)
        for w in (self.chunk, self.stride):
            w.setFixedWidth(70)
        r1, _ = self._row("Chunk", self.chunk, "chunk")
        r2, _ = self._row("Stride", self.stride, "stride")
        ml.addLayout(r1)
        ml.addLayout(r2)
        self.low_vram = QCheckBox("Low-VRAM mode")
        self._help("low_vram", self.low_vram)
        ml.addWidget(self.low_vram)
        self.temp = QLineEdit()
        self.temp.setPlaceholderText("Feature cache folder (default: system temp)")
        tl, _ = self._path_line(self.temp, "temp")
        ml.addLayout(tl)
        self.stage2 = QSpinBox()
        self.stage2.setRange(1, 16)
        self.stage2.setFixedWidth(70)
        r, _ = self._row("Stage 2 Batch", self.stage2, "stage2")
        ml.addLayout(r)
        sec.form.addWidget(self.manual)
        self.profile.currentIndexChanged.connect(self._commit)
        self.hann.currentIndexChanged.connect(self._hann_preset)
        self.chunk.valueChanged.connect(self._commit)
        self.stride.valueChanged.connect(self._commit)
        self.low_vram.toggled.connect(self._commit)
        self.temp.editingFinished.connect(self._commit)
        self.stage2.valueChanged.connect(self._commit)

    def _build_range(self) -> None:
        sec = self._section("FRAME RANGE")
        self.limit = QSpinBox()
        self.limit.setRange(0, 1_000_000)
        self.limit.setSpecialValueText("All")
        self.limit.setFixedWidth(90)
        r, _ = self._row("Frame Limit", self.limit, "limit")
        sec.form.addLayout(r)
        self.start = QComboBox()
        self.start.addItem("From start", "begin")
        self.start.addItem("Centered segment", "middle")
        self.start.addItem("Random middle", "random_middle")
        r, self.start_lab = self._row("Start", self.start, "start")
        sec.form.addLayout(r)
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.seed.setFixedWidth(90)
        r, self.seed_lab = self._row("Seed", self.seed, "seed")
        sec.form.addLayout(r)
        self.limit.valueChanged.connect(self._commit)
        self.start.currentIndexChanged.connect(self._commit)
        self.seed.valueChanged.connect(self._commit)

    def _build_output(self) -> None:
        sec = self._section("OUTPUT")
        self.out_checks: dict[str, QCheckBox] = {}
        for k in OUTPUT_KEYS:
            cb = QCheckBox(OUTPUT_LABELS[k])
            self._help("out_" + k, cb)
            cb.toggled.connect(self._commit)
            self.out_checks[k] = cb
            sec.form.addWidget(cb)
        self.fmt = QComboBox()
        self.fmt.addItem("Video previews", "video")
        self.fmt.addItem("EXR sequence (HDR)", "exr")
        r, _ = self._row("Format", self.fmt, "fmt")
        sec.form.addLayout(r)
        self.exr_dtype = QComboBox()
        self.exr_dtype.addItem("half (float16)", "half")
        self.exr_dtype.addItem("float (float32)", "float")
        r, self.dtype_lab = self._row("EXR Type", self.exr_dtype, "exr_dtype")
        sec.form.addLayout(r)
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Output folder (default: out_<clip> next to the clip)")
        ol, _ = self._path_line(self.out_dir, "out_dir")
        sec.form.addLayout(ol)
        self.fmt.currentIndexChanged.connect(self._commit)
        self.exr_dtype.currentIndexChanged.connect(self._commit)
        self.out_dir.editingFinished.connect(self._commit)

    def _build_encoding(self) -> None:
        sec = self._section("VIDEO ENCODING", collapsed=True)
        self.enc_widgets: list[QWidget] = []

        def add(label: str, w: QWidget, key: str):
            r, lab = self._row(label, w, key)
            sec.form.addLayout(r)
            self.enc_widgets.extend([lab, w])
            return lab

        self.enc_profile = QComboBox()
        self.enc_profile.addItem("Custom", None)
        for name in H.ENC_PROFILES:
            self.enc_profile.addItem(name, name)
        self.enc_profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.enc_profile.setMinimumContentsLength(14)
        self.enc_profile_lab = QLabel("Quick profile")
        sec.form.addWidget(self.enc_profile_lab)
        sec.form.addWidget(self.enc_profile)
        self._help("enc_profile", self.enc_profile_lab, self.enc_profile)
        self.enc_widgets += [self.enc_profile_lab, self.enc_profile]

        self.codec = QComboBox()
        self.codec.setEditable(True)
        self.codec.addItems(["libx264", "libx265"])
        add("Codec", self.codec, "codec")
        self.rate_mode = QComboBox()
        self.rate_mode.addItem("Quality (CRF)", "crf")
        self.rate_mode.addItem("Fixed bitrate", "bitrate")
        add("Rate control", self.rate_mode, "rate_mode")
        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setFixedWidth(70)
        self.crf_lab = add("CRF", self.crf, "crf")
        self.bitrate = QLineEdit()
        self.bitrate.setPlaceholderText("e.g. 50M or 8000k")
        self.bitrate.setValidator(QRegularExpressionValidator(BITRATE_RE, self.bitrate))
        self.bitrate.setFixedWidth(110)
        self.bitrate_lab = add("Bitrate", self.bitrate, "bitrate")
        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        add("Preset", self.preset, "preset")
        self.pix = QComboBox()
        self.pix.setEditable(True)
        self.pix.addItems(PIX_FMTS)
        add("Pixel Format", self.pix, "pix_fmt")
        self.threads = QSpinBox()
        self.threads.setRange(1, 64)
        self.threads.setFixedWidth(70)
        add("ffmpeg Threads", self.threads, "threads")
        self.frame_fps = QDoubleSpinBox()
        self.frame_fps.setRange(1.0, 240.0)
        self.frame_fps.setDecimals(3)
        self.frame_fps.setFixedWidth(90)
        self.fps_lab = add("Sequence Frame Rate", self.frame_fps, "frame_fps")

        note = QLabel("The Cutout is always written as ProRes 4444 so it keeps its transparency.")
        note.setWordWrap(True)
        T.sty(note, lambda: f"QLabel{{color:{T.c('TEXT_FAINT')}; font-size:10px;}}")
        sec.form.addWidget(note)
        self.enc_note = note
        self.enc_sec = sec

        self.enc_profile.activated.connect(self._enc_profile_picked)
        self.codec.currentTextChanged.connect(self._commit)
        self.rate_mode.currentIndexChanged.connect(self._commit)
        self.crf.valueChanged.connect(self._commit)
        self.bitrate.textChanged.connect(self._commit)
        self.preset.currentIndexChanged.connect(self._commit)
        self.pix.currentTextChanged.connect(self._commit)
        self.threads.valueChanged.connect(self._commit)
        self.frame_fps.valueChanged.connect(self._commit)

    # -- helpers -------------------------------------------------------------
    def _pick(self, line: QLineEdit, mode: str) -> None:
        if mode == "dir":
            p = QFileDialog.getExistingDirectory(self, "Choose folder", line.text())
        else:
            p, _ = QFileDialog.getOpenFileName(
                self, "Choose file", line.text(),
                "Media (*.png *.jpg *.jpeg *.exr *.mp4 *.mov *.avi *.mkv *.webm);;All files (*)")
        if p:
            line.setText(p)
            self._commit()

    def _hann_preset(self) -> None:
        if self._loading:
            return
        v = self.hann.currentData()
        if v:
            self._loading = True
            self.chunk.setValue(v[0])
            self.stride.setValue(v[1])
            self._loading = False
        self._commit()

    def _mode_changed(self) -> None:
        """A rough automatic hint deserves lower trust than a hand-made one (README: Hint Quality)."""
        if not self._loading:
            mode = self.hint_mode.currentData()
            if mode == "marker" and self._prev_mode != "marker" and self.hq.value() == 95:
                self._loading = True
                self.hq.setValue(75)
                self._loading = False
            elif self._prev_mode == "marker" and mode != "marker" and self.hq.value() == 75:
                self._loading = True
                self.hq.setValue(95)
                self._loading = False
            self._prev_mode = mode
        self._commit()

    def _enc_profile_picked(self, _i: int) -> None:
        name = self.enc_profile.currentData()
        if not name:
            return
        codec, crf, preset, pix = H.ENC_PROFILES[name]
        self._loading = True
        self.codec.setCurrentText(codec)
        self.crf.setValue(crf)
        self.preset.setCurrentText(preset)
        self.pix.setCurrentText(pix)
        self.rate_mode.setCurrentIndex(0)                  # profiles are quality based
        self.bitrate.setText("")
        self._loading = False
        self._commit()

    def _sync_enc_profile(self) -> None:
        cur = (self.codec.currentText().strip(), self.crf.value(), self.preset.currentText(),
               self.pix.currentText().strip())
        name = next((n for n, v in H.ENC_PROFILES.items() if v == cur), None)
        if self.rate_mode.currentData() != "crf":
            name = None
        was = self._loading
        self._loading = True
        self.enc_profile.setCurrentIndex(max(self.enc_profile.findData(name), 0) if name else 0)
        self._loading = was

    def _sync_labels(self) -> None:
        self.hq_lab.setText(f"Hint Quality: {self.hq.value() / 100:.2f}")
        self.cq_lab.setText(f"Carry Quality: {self.cq.value() / 100:.2f}")
        self.despill_lab.setText(f"Despill: {self.despill.value() / 100:.2f}")
        g, sf = self.mk_grow.value() / 10.0, self.mk_soft.value() / 10.0
        self.mk_grow_lab.setText(f"Grow / shrink: {g:+.1f}%")
        self.mk_soft_lab.setText(f"Edge softness: {sf:.1f}%")

    def _sync_enabled(self) -> None:
        has = self.s is not None
        mode = self.hint_mode.currentData()
        video = self.kind == "video"
        exr = self.fmt.currentData() == "exr"
        manual = not self.profile.currentData()
        marker = mode == "marker"
        self.path_row.setVisible(not marker)
        self.marker_box.setVisible(marker)
        self.marker_box.setEnabled(has)
        if not marker and self.mk_place.isChecked():
            was = self._loading
            self._loading = True
            self.mk_place.setChecked(False)
            self._loading = was
        self.hint_path.setEnabled(has and mode in ("first", "video"))
        self.hint_file.setEnabled(has and mode in ("first", "video"))
        self.hint_dir.setEnabled(has and mode in ("first", "video"))
        self.hq.setEnabled(has and mode != "none")
        carry_on = has and mode != "none" and not (mode == "video" and self.no_carry.isChecked())
        self.cq.setEnabled(carry_on)
        self.no_carry.setEnabled(has and mode == "video")
        self.space.setEnabled(has and not video)
        self.cutout_linear.setEnabled(has and not exr and self.out_checks["cutout"].isChecked())
        self.manual.setEnabled(has and manual)
        custom = self.hann.currentData() is None
        self.chunk.setEnabled(has and manual and custom)
        self.stride.setEnabled(has and manual and custom)
        self.temp.setEnabled(has and manual and self.low_vram.isChecked())
        self.start.setEnabled(has and video and self.limit.value() > 0)
        self.seed.setEnabled(has and video and self.limit.value() > 0
                             and self.start.currentData() == "random_middle")
        self.exr_dtype.setEnabled(has and exr)
        for w in self.enc_widgets:
            w.setEnabled(has and not exr)
        if has and not exr:
            by_bitrate = self.rate_mode.currentData() == "bitrate"
            self.crf.setEnabled(not by_bitrate)
            self.crf_lab.setEnabled(not by_bitrate)
            self.bitrate.setEnabled(by_bitrate)
            self.bitrate_lab.setEnabled(by_bitrate)
            self.frame_fps.setEnabled(self.kind == "sequence")
            self.fps_lab.setEnabled(self.kind == "sequence")
        self.enc_note.setEnabled(has and not exr)

    # -- state <-> widgets ----------------------------------------------------
    def set_settings(self, s: Optional[Settings], kind: str = "video") -> None:
        self.s, self.kind = s, kind
        self._loading = True
        d = s if s is not None else Settings()
        self.hint_mode.setCurrentIndex(max(self.hint_mode.findData(d.hint_mode), 0))
        self._prev_mode = self.hint_mode.currentData()
        self.hint_path.setText(d.hint_path)
        self.hq.setValue(round(d.hint_quality * 100))
        self.cq.setValue(round(d.carry_quality * 100))
        self.no_carry.setChecked(d.no_carry)
        self.mk_grow.setValue(d.marker_grow)
        self.mk_soft.setValue(d.marker_soft)
        self.space.setCurrentIndex(1 if d.frame_linear else 0)
        self.despill.setValue(round(d.despill * 100))
        self.cutout_linear.setChecked(d.cutout_linear)
        self.scale.setValue(d.model_scale)
        self.profile.setCurrentIndex(0 if d.auto_vram else 1)
        self.chunk.setValue(d.hann_chunk)
        self.stride.setValue(d.hann_stride)
        idx = next((i for i, (_, c, st) in enumerate(HANN_PRESETS)
                    if (c, st) == (d.hann_chunk, d.hann_stride)), len(HANN_PRESETS))
        self.hann.setCurrentIndex(idx)
        self.low_vram.setChecked(d.low_vram)
        self.temp.setText(d.temp_dir)
        self.stage2.setValue(d.stage2_batch)
        self.limit.setValue(d.num_frames)
        self.start.setCurrentIndex(max(self.start.findData(d.start_mode), 0))
        self.seed.setValue(d.seed)
        for k, cb in self.out_checks.items():
            cb.setChecked(k in d.outputs)
        self.fmt.setCurrentIndex(max(self.fmt.findData(d.output_format), 0))
        self.exr_dtype.setCurrentIndex(max(self.exr_dtype.findData(d.exr_dtype), 0))
        self.out_dir.setText(d.out_dir)
        self.codec.setCurrentText(d.codec)
        self.crf.setValue(d.crf)
        self.bitrate.setText(d.bitrate)
        self.rate_mode.setCurrentIndex(1 if d.bitrate.strip() else 0)
        self.preset.setCurrentText(d.preset)
        self.pix.setCurrentText(d.pix_fmt)
        self.threads.setValue(d.threads)
        self.frame_fps.setValue(d.frame_fps)
        self._loading = False
        self._sync_enc_profile()
        self._sync_labels()
        self._sync_enabled()

    def set_marker_status(self, text: str, ok: bool = True) -> None:
        self._mk_ok = ok
        self.mk_status.setText(text)
        self.mk_status.setStyleSheet(self._status_css())

    def set_marker_mode(self, on: bool) -> None:
        """Set the PLACE MARKERS toggle without telling anyone (the caller already knows)."""
        was = self._loading
        self._loading = True
        self.mk_place.setChecked(bool(on))
        self._loading = was

    @property
    def marker_mode(self) -> bool:
        return self.mk_place.isChecked() and self.hint_mode.currentData() == "marker"

    def _commit(self, *_):
        if self._loading:
            return
        self._sync_labels()
        s = self.s
        if s is not None:
            s.hint_mode = self.hint_mode.currentData()
            s.hint_path = self.hint_path.text().strip() if s.hint_mode != "marker" else s.hint_path
            s.hint_quality = self.hq.value() / 100
            s.carry_quality = self.cq.value() / 100
            s.no_carry = self.no_carry.isChecked()
            s.marker_grow = self.mk_grow.value()
            s.marker_soft = self.mk_soft.value()
            if self.kind == "sequence":
                s.frame_linear = bool(self.space.currentData())
                s.frame_fps = round(self.frame_fps.value(), 3)
            s.despill = self.despill.value() / 100
            s.cutout_linear = self.cutout_linear.isChecked()
            s.model_scale = round(self.scale.value(), 2)
            s.auto_vram = bool(self.profile.currentData())
            s.hann_chunk = self.chunk.value()
            s.hann_stride = self.stride.value()
            s.low_vram = self.low_vram.isChecked()
            s.temp_dir = self.temp.text().strip()
            s.stage2_batch = self.stage2.value()
            s.num_frames = self.limit.value()
            s.start_mode = self.start.currentData()
            s.seed = self.seed.value()
            s.outputs = [k for k in OUTPUT_KEYS if self.out_checks[k].isChecked()]
            s.output_format = self.fmt.currentData()
            s.exr_dtype = self.exr_dtype.currentData()
            s.out_dir = self.out_dir.text().strip()
            s.codec = self.codec.currentText().strip() or "libx264"
            s.crf = self.crf.value()
            s.preset = self.preset.currentText()
            s.pix_fmt = self.pix.currentText().strip() or "yuv444p10le"
            s.bitrate = (self.bitrate.text().strip()
                         if self.rate_mode.currentData() == "bitrate" and self.bitrate.hasAcceptableInput() else "")
            s.threads = self.threads.value()
        self._sync_enc_profile()
        self._sync_enabled()
        self.edited.emit()
