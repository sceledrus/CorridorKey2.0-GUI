"""Settings window: General (paths, help), Appearance (Dark / Light / Custom theme maker), Sound.

The dialog edits a copy of the preferences. Colour changes are previewed live on the real window (the
whole app re-themes as you click) and are undone if you press Cancel - the main window handles that through
the `themePreview` signal.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QRadioButton, QSlider, QTabWidget, QVBoxLayout,
                               QWidget)

from . import sound as SND
from . import theme as T

AUDIO_FILTER = "Audio (" + " ".join("*" + e for e in SND.CUSTOM_EXTS) + ");;All files (*)"
HEX_RE = QRegularExpression(r"^#[0-9a-fA-F]{6}$")

DEFAULT_PREFS = {
    "out_dir": "", "ffmpeg": "", "python": "", "infer": "",
    "theme": "dark", "custom_theme": dict(T.CUSTOM_BASES["dark"]),
    "sound_on": True, "sound_chime": SND.DEFAULT_CHIME, "sound_custom": "", "sound_use_custom": False,
    "sound_volume": 80, "help_on": True,
}


def normalised_custom(d: Optional[dict]) -> dict:
    base = dict(T.CUSTOM_BASES["dark"])
    for k, v in (d or {}).items():
        if k in base and T.is_valid_hex(v):
            base[k] = _six(v)
    return base


def _six(h: str) -> str:
    h = h.lower()
    return "#" + "".join(ch * 2 for ch in h[1:]) if len(h) == 4 else h


class ColorRow(QWidget):
    changed = Signal(str, str)           # key, "#rrggbb"

    def __init__(self, key: str, label: str, value: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._val = value
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        lab = QLabel(label)
        lab.setMinimumWidth(130)
        self.swatch = QPushButton()
        self.swatch.setFixedSize(46, 24)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.setToolTip("Click to pick a colour")
        self.edit = QLineEdit()
        self.edit.setFixedWidth(88)
        self.edit.setMaxLength(7)
        self.edit.setValidator(QRegularExpressionValidator(HEX_RE, self.edit))
        self.edit.setPlaceholderText("#rrggbb")
        h.addWidget(lab)
        h.addWidget(self.swatch)
        h.addWidget(self.edit)
        h.addStretch(1)
        self.set_value(value)
        self.swatch.clicked.connect(self._pick)
        self.edit.editingFinished.connect(self._typed)

    def value(self) -> str:
        return self._val

    def set_value(self, v: str) -> None:
        v = _six(v)
        self._val = v
        self.edit.setText(v)
        self.swatch.setStyleSheet(f"QPushButton{{background:{v}; border:1px solid #888; border-radius:3px;}}")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.value()), self, "Pick a colour")
        if c.isValid():
            self.set_value(c.name())
            self.changed.emit(self.key, self.value())

    def _typed(self) -> None:
        v = self.edit.text()
        if T.is_valid_hex(v) and len(v) == 7:
            self.set_value(v)
            self.changed.emit(self.key, v)
        else:
            self.set_value(self._val)


class SettingsDialog(QDialog):
    themePreview = Signal(str, dict)

    def __init__(self, parent, prefs: dict, player: SND.SoundPlayer, auto_paths: dict[str, str],
                 config_dir: str = "", open_folder: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(660, 560)
        self.p = {**DEFAULT_PREFS, **prefs}
        self.p["custom_theme"] = normalised_custom(self.p.get("custom_theme"))
        self.player = player
        self.config_dir = config_dir
        self.open_folder = open_folder

        v = QVBoxLayout(self)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.tabs.addTab(self._general(auto_paths), "General")
        self.tabs.addTab(self._appearance(), "Appearance")
        self.tabs.addTab(self._sound(), "Sound")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    # ---------------------------------------------------------------- General
    def _path_row(self, key: str, placeholder: str, pick: str) -> tuple[QWidget, QLineEdit]:
        e = QLineEdit(self.p.get(key, ""))
        e.setPlaceholderText(placeholder)
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(e, 1)
        b = QPushButton("...")
        b.setObjectName("ghost")
        b.setFixedWidth(34)

        def choose():
            p = (QFileDialog.getExistingDirectory(self, "Choose folder", e.text()) if pick == "dir"
                 else QFileDialog.getOpenFileName(self, "Choose file", e.text())[0])
            if p:
                e.setText(p)
        b.clicked.connect(choose)
        h.addWidget(b)
        return w, e

    def _general(self, auto: dict[str, str]) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        row, self.f_out = self._path_row("out_dir", "Next to each clip (out_<clip>)", "dir")
        form.addRow("Default output folder", row)
        row, self.f_python = self._path_row("python", "Auto: " + auto.get("python", ""), "file")
        form.addRow("Python executable", row)
        row, self.f_ffmpeg = self._path_row("ffmpeg", "Auto: ffmpeg on PATH", "file")
        form.addRow("ffmpeg executable", row)
        row, self.f_infer = self._path_row("infer", "Auto: " + auto.get("infer", ""), "file")
        form.addRow("infer.py", row)
        self.f_python.setToolTip("The Python that has PyTorch + CUDA installed (normally the repo's venv).")
        self.f_ffmpeg.setToolTip("Used for the result videos. Also used to convert your own completion sound.")
        self.help_on = QCheckBox("Show hover explanations (tooltips next to the mouse)")
        self.help_on.setChecked(bool(self.p.get("help_on", True)))
        self.help_on.setToolTip("Hover any section header or setting for a plain-language explanation. "
                                "Turn this off once you know your way around.")
        form.addRow("Help", self.help_on)
        if self.config_dir:
            r = QWidget()
            h = QHBoxLayout(r)
            h.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(self.config_dir)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setWordWrap(True)
            h.addWidget(lab, 1)
            if self.open_folder:
                b = QPushButton("OPEN")
                b.setObjectName("ghost")
                b.clicked.connect(lambda: self.open_folder(self.config_dir))
                h.addWidget(b)
            form.addRow("Settings folder", r)
        return w

    # ------------------------------------------------------------- Appearance
    def _appearance(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        top = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        self.theme_radio: dict[str, QRadioButton] = {}
        for name, label in T.THEME_NAMES.items():
            r = QRadioButton(label)
            self.theme_group.addButton(r)
            self.theme_radio[name] = r
            top.addWidget(r)
            r.toggled.connect(lambda on, n=name: on and self._theme_chosen(n))
        top.addStretch(1)
        v.addLayout(top)
        blurb = QLabel("Dark is the Corridor look. Light is a clean white theme. Custom lets you pick six colours - "
                       "everything else (borders, hover states, disabled looks) is worked out from them. "
                       "Changes preview live on the window behind this one and are undone if you press Cancel.")
        blurb.setWordWrap(True)
        v.addWidget(blurb)

        self.custom_box = QGroupBox("Custom theme maker")
        cv = QVBoxLayout(self.custom_box)
        cv.setSpacing(8)
        self.rows: dict[str, ColorRow] = {}
        cur = self.p["custom_theme"]
        for key, label in T.CUSTOM_FIELDS:
            row = ColorRow(key, label, cur[key])
            row.changed.connect(self._color_changed)
            self.rows[key] = row
            cv.addWidget(row)
        self.read_note = QLabel()
        self.read_note.setWordWrap(True)
        cv.addWidget(self.read_note)
        br = QHBoxLayout()
        self.start_from = QComboBox()
        for n in ("dark", "light"):
            self.start_from.addItem("Start from " + T.THEME_NAMES[n], n)
        self.start_from.setToolTip("Reset the six colours to one of the built-in themes, then tweak from there.")
        self.start_from.activated.connect(self._start_from)
        self.btn_export = QPushButton("EXPORT...")
        self.btn_export.setObjectName("ghost")
        self.btn_import = QPushButton("IMPORT...")
        self.btn_import.setObjectName("ghost")
        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        br.addWidget(self.start_from)
        br.addStretch(1)
        br.addWidget(self.btn_export)
        br.addWidget(self.btn_import)
        cv.addLayout(br)
        v.addWidget(self.custom_box)
        v.addStretch(1)

        name = self.p.get("theme", "dark")
        self.theme_name = name if name in T.THEME_NAMES else "dark"
        self.theme_radio[self.theme_name].setChecked(True)
        self._sync_theme_ui()
        return w

    def custom_colors(self) -> dict:
        return {k: r.value() for k, r in self.rows.items()}

    def _sync_theme_ui(self) -> None:
        self.custom_box.setEnabled(self.theme_name == "custom")
        c = self.custom_colors()
        ratio = T.contrast(c["text"], c["bg"])
        ratio_p = T.contrast(c["text"], c["panel"])
        worst = min(ratio, ratio_p)
        if worst < 3.0:
            msg, col = f"Text is very hard to read on these backgrounds (contrast {worst:.1f}:1). Try a lighter or darker text colour.", "RED"
        elif worst < 4.5:
            msg, col = f"Text is a little low-contrast ({worst:.1f}:1). It works, but a stronger text colour reads better.", "ORANGE"
        else:
            msg, col = f"Text contrast {worst:.1f}:1 - easy to read.", "TEXT_DIM"
        self.read_note.setText(msg)
        self.read_note.setStyleSheet(f"QLabel{{color:{T.c(col)};}}")

    def _emit_preview(self) -> None:
        self.themePreview.emit(self.theme_name, self.custom_colors())

    def _theme_chosen(self, name: str) -> None:
        self.theme_name = name
        self._sync_theme_ui()
        self._emit_preview()

    def _color_changed(self, _k: str, _v: str) -> None:
        if self.theme_name != "custom":
            self.theme_radio["custom"].setChecked(True)      # triggers _theme_chosen
            return
        self._sync_theme_ui()
        self._emit_preview()

    def _start_from(self, _i: int) -> None:
        base = T.CUSTOM_BASES[self.start_from.currentData()]
        for k, r in self.rows.items():
            r.set_value(base[k])
        if self.theme_name != "custom":
            self.theme_radio["custom"].setChecked(True)
        else:
            self._sync_theme_ui()
            self._emit_preview()

    def export_theme(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"corridorkey_theme": 1, "colors": self.custom_colors()}, f, indent=2)

    def import_theme(self, path: str) -> None:
        """Load six colours from a theme .json. Raises ValueError / OSError if the file is not usable."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        colors = data.get("colors", data) if isinstance(data, dict) else {}
        good = {k: _six(v) for k, v in colors.items() if k in self.rows and T.is_valid_hex(v)}
        if not good:
            raise ValueError("no colours found in that file")
        for k, v in good.items():
            self.rows[k].set_value(v)
        self.theme_radio["custom"].setChecked(True)
        self._sync_theme_ui()
        self._emit_preview()

    def _export(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Export theme", "my_corridorkey_theme.json", "Theme (*.json)")
        if p:
            try:
                self.export_theme(p)
            except OSError as e:
                QMessageBox.warning(self, "Export theme", f"Could not save the theme: {e}")

    def _import(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Import theme", "", "Theme (*.json);;All files (*)")
        if p:
            try:
                self.import_theme(p)
            except (OSError, ValueError) as e:       # json.JSONDecodeError is a ValueError
                QMessageBox.warning(self, "Import theme", f"That file is not a usable theme: {e}")

    # ---------------------------------------------------------------- Sound
    def _sound(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        self.sound_on = QCheckBox("Play a sound when a render finishes")
        self.sound_on.setChecked(bool(self.p.get("sound_on", True)))
        self.sound_on.setToolTip("Plays once, when the whole queue is finished and at least one clip succeeded. "
                                 "Failed or cancelled runs stay quiet.")
        v.addWidget(self.sound_on)

        box = QGroupBox("Built-in sound")
        bl = QFormLayout(box)
        self.chime = QComboBox()
        for k, (label, _d) in SND.CHIMES.items():
            self.chime.addItem(label, k)
        self.chime.setCurrentIndex(max(self.chime.findData(self.p.get("sound_chime", SND.DEFAULT_CHIME)), 0))
        self.chime_desc = QLabel()
        self.chime.currentIndexChanged.connect(self._chime_changed)
        bl.addRow("Sound", self.chime)
        bl.addRow("", self.chime_desc)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(self.p.get("sound_volume", 80)))
        self.vol_lab = QLabel()
        self.volume.valueChanged.connect(lambda x: self.vol_lab.setText(f"{x}%"))
        self.vol_lab.setText(f"{self.volume.value()}%")
        vr = QHBoxLayout()
        vr.addWidget(self.volume, 1)
        vr.addWidget(self.vol_lab)
        bl.addRow("Volume", vr)
        v.addWidget(box)
        self._chime_changed()

        cbox = QGroupBox("Your own sound")
        cl = QVBoxLayout(cbox)
        self.use_custom = QCheckBox("Use my own audio clip instead of the built-in sound")
        self.use_custom.setChecked(bool(self.p.get("sound_use_custom")))
        cl.addWidget(self.use_custom)
        pr = QHBoxLayout()
        self.custom_path = QLineEdit(self.p.get("sound_custom", ""))
        self.custom_path.setReadOnly(True)
        self.custom_path.setPlaceholderText("No file chosen")
        bb = QPushButton("BROWSE...")
        bb.setObjectName("ghost")
        bc = QPushButton("CLEAR")
        bc.setObjectName("ghost")
        bb.clicked.connect(self._browse_sound)
        bc.clicked.connect(self._clear_sound)
        pr.addWidget(self.custom_path, 1)
        pr.addWidget(bb)
        pr.addWidget(bc)
        cl.addLayout(pr)
        self.sound_msg = QLabel("WAV, MP3, OGG, FLAC, M4A... Anything that is not a plain WAV is converted once "
                                "(needs ffmpeg) and only the first %g seconds are used." % SND.MAX_CUSTOM_SECONDS)
        self.sound_msg.setWordWrap(True)
        cl.addWidget(self.sound_msg)
        v.addWidget(cbox)

        tr = QHBoxLayout()
        self.btn_test = QPushButton("▶  TEST SOUND")
        self.btn_test.clicked.connect(self.test_sound)
        tr.addWidget(self.btn_test)
        tr.addStretch(1)
        v.addLayout(tr)
        v.addStretch(1)
        return w

    def _chime_changed(self) -> None:
        self.chime_desc.setText(SND.CHIMES[self.chime.currentData()][1])

    def _browse_sound(self) -> None:
        start = os.path.dirname(self.custom_path.text()) if self.custom_path.text() else ""
        p, _ = QFileDialog.getOpenFileName(self, "Choose your completion sound", start, AUDIO_FILTER)
        if not p:
            return
        self.set_custom_sound(p)

    def set_custom_sound(self, path: str) -> bool:
        wav, msg = SND.prepare_custom(path, self.player.cache_dir, self.f_ffmpeg.text().strip())
        if wav:
            self.custom_path.setText(path)
            self.use_custom.setChecked(True)
            self.sound_msg.setText(msg)
            return True
        self.sound_msg.setText(msg)
        return False

    def _clear_sound(self) -> None:
        self.custom_path.setText("")
        self.use_custom.setChecked(False)
        self.sound_msg.setText("Back to the built-in sound.")

    def test_sound(self) -> bool:
        ok = self.player.play(self.chime.currentData(), self.custom_path.text(), self.use_custom.isChecked(),
                              self.volume.value() / 100.0, self.f_ffmpeg.text().strip())
        if self.player.last_message:
            self.sound_msg.setText(self.player.last_message)
        return ok

    # ---------------------------------------------------------------- result
    def values(self) -> dict:
        return {
            "out_dir": self.f_out.text().strip(), "python": self.f_python.text().strip(),
            "ffmpeg": self.f_ffmpeg.text().strip(), "infer": self.f_infer.text().strip(),
            "theme": self.theme_name, "custom_theme": self.custom_colors(),
            "sound_on": self.sound_on.isChecked(), "sound_chime": self.chime.currentData(),
            "sound_custom": self.custom_path.text(),
            "sound_use_custom": self.use_custom.isChecked() and bool(self.custom_path.text()),
            "sound_volume": self.volume.value(), "help_on": self.help_on.isChecked(),
        }
