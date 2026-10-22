"""Palettes, stylesheet and generated icon assets.

The default (dark) look follows the Corridor Key 1 desktop GUI: near-black olive surfaces, a yellow
accent, green slider thumbs, tiny uppercase section labels. Colours were sampled from that GUI;
nothing here is copied from its code.

Everything that draws or styles itself reads colours from this module's attributes (ACCENT,
BG_PANEL, ...), and ``set_theme`` rewrites those attributes, so a theme change can be applied to
a running window: ``retheme(app)`` regenerates the application stylesheet and re-runs every
inline style registered through ``sty`` / ``style_box``.
"""
from __future__ import annotations

import os
import tempfile
import weakref
from typing import Callable, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QPolygonF

# --------------------------------------------------------------------------
# palettes (pure Python: no Qt needed to build or test them)
# --------------------------------------------------------------------------
DARK = {
    "ACCENT": "#fff203", "ACCENT_FG": "#fff203", "ACCENT_DIM": "#cabf00", "ACCENT_DARK": "#8a8400",
    "ACCENT_HOVER": "#fffa5c", "TEXT_ON_ACCENT": "#141300",
    "GREEN": "#2bc44f", "GREEN_HOVER": "#4ee070", "GREEN_OFF": "#1c4a2a",
    "RED": "#e5484d", "ORANGE": "#f08c2e", "BLUE": "#4aa3ff",
    "BG_VIEW": "#0a0a02", "BG_ROOT": "#0a0a00", "BG_BAR": "#0f0d00", "BG_BRAND": "#121001",
    "BG_PANEL": "#1d1d15", "BG_FIELD": "#1a1800", "BG_BTN": "#2a280f", "BG_BTN_OFF": "#1a1800",
    "BG_MENU": "#15130a", "BG_DEEP": "#050500", "BG_CARD": "#100e00", "BG_ROW": "#14120a",
    "BG_CONSOLE": "#0c0b00", "BG_DISABLED": "#131100",
    "LINE": "#27271d", "LINE_MID": "#3a3712", "LINE_FIELD": "#3d3a14", "LINE_DISABLED": "#24220c",
    "TEXT": "#d8d6c2", "TEXT_DIM": "#8f8c6e", "TEXT_FAINT": "#4c4936", "TEXT_BRIGHT": "#f0eed8",
    "SCRUB_A": "#5a5742", "SCRUB_B": "#3a3822", "MARK": "#d9d7c4",
    "PRIMARY_OFF": "#4a4700", "PRIMARY_OFF_TEXT": "#1a1800",
    "BTN2_BG": "#6b6600", "BTN2_FG": "#fff9a0", "BTN2_HOVER": "#8a8400", "BTN2_OFF_BG": "#2a2800",
    "STOP_BG": "#3a1417", "STOP_FG": "#ff9a9d", "STOP_HOVER": "#55191d",
    "TOOLTIP_BG": "#15130a", "TOOLTIP_FG": "#eceacd",
}

LIGHT = {
    "ACCENT": "#e0b800", "ACCENT_FG": "#8a6d00", "ACCENT_DIM": "#b99600", "ACCENT_DARK": "#a88300",
    "ACCENT_HOVER": "#f2cc2e", "TEXT_ON_ACCENT": "#1a1800",
    "GREEN": "#1f9d3f", "GREEN_HOVER": "#2bb852", "GREEN_OFF": "#a9d8b6",
    "RED": "#d12f35", "ORANGE": "#d97a12", "BLUE": "#1f7ae0",
    "BG_VIEW": "#e4e4dc", "BG_ROOT": "#f3f3ef", "BG_BAR": "#e9e9e3", "BG_BRAND": "#ffffff",
    "BG_PANEL": "#fafaf7", "BG_FIELD": "#ffffff", "BG_BTN": "#e4e3da", "BG_BTN_OFF": "#eeeee8",
    "BG_MENU": "#ffffff", "BG_DEEP": "#d6d6cd", "BG_CARD": "#ffffff", "BG_ROW": "#ffffff",
    "BG_CONSOLE": "#ffffff", "BG_DISABLED": "#efefe9",
    "LINE": "#d2d2c8", "LINE_MID": "#c4c3b2", "LINE_FIELD": "#bdbcab", "LINE_DISABLED": "#dcdcd2",
    "TEXT": "#23221a", "TEXT_DIM": "#625f48", "TEXT_FAINT": "#a09d86", "TEXT_BRIGHT": "#14130a",
    "SCRUB_A": "#9c9a82", "SCRUB_B": "#c6c4b0", "MARK": "#3b3a2c",
    "PRIMARY_OFF": "#e9dd95", "PRIMARY_OFF_TEXT": "#9a9578",
    "BTN2_BG": "#efe3a0", "BTN2_FG": "#4a4200", "BTN2_HOVER": "#e6d57a", "BTN2_OFF_BG": "#ecebe2",
    "STOP_BG": "#fde7e8", "STOP_FG": "#b3202a", "STOP_HOVER": "#fbd3d5",
    "TOOLTIP_BG": "#fffbe0", "TOOLTIP_FG": "#23221a",
}

# The handful of colours the custom-theme maker exposes; everything else is derived from them.
CUSTOM_FIELDS = [
    ("bg", "Background"), ("panel", "Panels"), ("text", "Text"),
    ("accent", "Accent"), ("ok", "Success / sliders"), ("danger", "Danger"),
]
CUSTOM_BASES = {
    "dark": {"bg": "#0a0a00", "panel": "#1d1d15", "text": "#d8d6c2",
             "accent": "#fff203", "ok": "#2bc44f", "danger": "#e5484d"},
    "light": {"bg": "#f3f3ef", "panel": "#fafaf7", "text": "#23221a",
              "accent": "#e0b800", "ok": "#1f9d3f", "danger": "#d12f35"},
}
THEME_NAMES = {"dark": "Dark (Corridor)", "light": "Light (White)", "custom": "Custom"}


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a: str, b: str, t: float) -> str:
    """a moved a fraction t of the way towards b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def luma(h: str) -> float:
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luma(a), luma(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def is_valid_hex(s: object) -> bool:
    if not isinstance(s, str) or not s.startswith("#") or len(s) not in (4, 7):
        return False
    try:
        _rgb(s)
        return True
    except ValueError:
        return False


def derive(base: dict) -> dict:
    """Full palette from the six custom-theme colours (missing/invalid ones fall back to Dark)."""
    b = dict(CUSTOM_BASES["dark"])
    b.update({k: v for k, v in (base or {}).items() if k in b and is_valid_hex(v)})
    bg, panel, text, accent, ok, danger = (b[k] for k in ("bg", "panel", "text", "accent", "ok", "danger"))
    dark = luma(bg) < 0.4
    white, black = "#ffffff", "#000000"
    # accent used as *text* must stay readable on the background
    accent_fg = accent
    for _ in range(12):
        if contrast(accent_fg, bg) >= 3.0:
            break
        accent_fg = mix(accent_fg, white if dark else black, 0.15)
    btn2 = mix(accent, bg, 0.55) if dark else mix(accent, white, 0.6)
    p = {
        "ACCENT": accent, "ACCENT_FG": accent_fg, "ACCENT_DIM": mix(accent, bg, 0.2),
        "ACCENT_DARK": mix(accent, bg, 0.45), "ACCENT_HOVER": mix(accent, white, 0.35),
        "TEXT_ON_ACCENT": "#141300" if luma(accent) > 0.3 else white,
        "GREEN": ok, "GREEN_HOVER": mix(ok, white, 0.25), "GREEN_OFF": mix(ok, bg, 0.7),
        "RED": danger, "ORANGE": DARK["ORANGE"] if dark else LIGHT["ORANGE"],
        "BLUE": DARK["BLUE"] if dark else LIGHT["BLUE"],
        "BG_ROOT": bg, "BG_BAR": mix(bg, text, 0.035), "BG_BRAND": mix(bg, text, 0.06),
        "BG_PANEL": panel, "BG_FIELD": mix(panel, bg, 0.5), "BG_BTN": mix(panel, text, 0.10),
        "BG_BTN_OFF": mix(panel, bg, 0.5), "BG_MENU": mix(panel, bg, 0.3),
        "BG_VIEW": mix(bg, black, 0.25 if dark else 0.06),
        "BG_DEEP": mix(bg, black, 0.5 if dark else 0.12),
        "BG_CARD": mix(bg, text, 0.04), "BG_ROW": mix(bg, text, 0.055),
        "BG_CONSOLE": mix(bg, black, 0.2) if dark else bg, "BG_DISABLED": mix(panel, bg, 0.7),
        "LINE": mix(bg, text, 0.14), "LINE_MID": mix(bg, text, 0.20),
        "LINE_FIELD": mix(bg, text, 0.26), "LINE_DISABLED": mix(bg, text, 0.10),
        "TEXT": text, "TEXT_DIM": mix(text, bg, 0.42), "TEXT_FAINT": mix(text, bg, 0.72),
        "TEXT_BRIGHT": mix(text, white if dark else black, 0.4),
        "SCRUB_A": mix(bg, text, 0.35), "SCRUB_B": mix(bg, text, 0.2), "MARK": mix(text, bg, 0.1),
        "PRIMARY_OFF": mix(accent, bg, 0.72), "PRIMARY_OFF_TEXT": mix(accent, bg, 0.45),
        "BTN2_BG": btn2, "BTN2_FG": mix(accent, white, 0.5) if dark else mix(accent, black, 0.65),
        "BTN2_HOVER": mix(btn2, accent, 0.5), "BTN2_OFF_BG": mix(panel, bg, 0.4),
        "STOP_BG": mix(danger, bg, 0.8), "STOP_FG": mix(danger, white if dark else black, 0.55),
        "STOP_HOVER": mix(danger, bg, 0.7),
    }
    p["TOOLTIP_BG"] = p["BG_MENU"]
    p["TOOLTIP_FG"] = p["TEXT_BRIGHT"]
    return p


# --------------------------------------------------------------------------
# current palette: module attributes, rewritten by set_theme()
# --------------------------------------------------------------------------
KEYS = tuple(DARK)
CURRENT = "dark"
STATUS_COLORS: dict[str, str] = {}

FONT_STACK = ["Segoe UI", "Open Sans", "Inter", "Noto Sans", "Helvetica Neue",
              "DejaVu Sans", "Arial"]
MONO_STACK = ["Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono",
              "Menlo", "Courier New"]


def palette_for(name: str, custom: Optional[dict] = None) -> dict:
    if name == "light":
        return dict(LIGHT)
    if name == "custom":
        return derive(custom or {})
    return dict(DARK)


def set_theme(name: str = "dark", custom: Optional[dict] = None) -> dict:
    """Make `name` (dark | light | custom) the current palette. Safe to call before any widget exists."""
    global CURRENT
    pal = palette_for(name, custom)
    CURRENT = name if name in THEME_NAMES else "dark"
    globals().update(pal)
    STATUS_COLORS.clear()
    STATUS_COLORS.update({
        "READY": pal["ACCENT_FG"], "QUEUED": pal["TEXT_DIM"], "RUNNING": pal["ACCENT_FG"],
        "COMPLETE": pal["GREEN"], "DONE": pal["GREEN"], "ERROR": pal["RED"],
        "CANCELLED": pal["ORANGE"],
    })
    return pal


set_theme("dark")


def qcolor(key_or_hex: str) -> QColor:
    return QColor(globals().get(key_or_hex, key_or_hex))


def c(key_or_hex: str) -> str:
    """Palette key -> current hex (a plain hex string passes through)."""
    return globals().get(key_or_hex, key_or_hex) if key_or_hex in KEYS else key_or_hex


# --------------------------------------------------------------------------
# inline styles that must follow theme changes
# --------------------------------------------------------------------------
_registry: list[tuple] = []


def sty(widget, css_fn: Callable[[], str]) -> None:
    """Apply css_fn() to the widget now and again after every theme change."""
    widget.setStyleSheet(css_fn())
    _registry.append((weakref.ref(widget), css_fn))


def restyle_all() -> None:
    alive = []
    for ref, fn in _registry:
        w = ref()
        if w is None:
            continue
        try:
            w.setStyleSheet(fn())
        except RuntimeError:           # the C++ widget is already gone
            continue
        alive.append((ref, fn))
    _registry[:] = alive


# --------------------------------------------------------------------------
# generated arrow icons (QSS needs image files for combo/spin arrows)
# --------------------------------------------------------------------------
def _asset_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "ck2_gui_assets")
    os.makedirs(d, exist_ok=True)
    return d


def _arrow_png(up: bool, color: str, size: int = 10) -> str:
    # colour is part of the file name: Qt caches QSS images by path, so a theme change needs a new path
    path = os.path.join(_asset_dir(), f"arrow_{'up' if up else 'down'}_{color.lstrip('#')}.png")
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        m = 2
        if up:
            tri = QPolygonF([QPointF(m, size - m - 1), QPointF(size - m, size - m - 1),
                             QPointF(size / 2, m)])
        else:
            tri = QPolygonF([QPointF(m, m + 1), QPointF(size - m, m + 1),
                             QPointF(size / 2, size - m)])
        p.drawPolygon(tri)
        p.end()
        pm.save(path, "PNG")
    return path.replace("\\", "/")


def stylesheet() -> str:
    g = globals()
    P = {k: g[k] for k in KEYS}
    down = _arrow_png(False, P["TEXT_DIM"])
    up = _arrow_png(True, P["TEXT_DIM"])
    down_hi = _arrow_png(False, P["ACCENT_FG"])
    up_hi = _arrow_png(True, P["ACCENT_FG"])
    return f"""
* {{ color: {P['TEXT']}; font-size: 12px; }}
QMainWindow, QWidget#root {{ background: {P['BG_ROOT']}; }}
QWidget {{ background: transparent; }}
QToolTip {{ background: {P['TOOLTIP_BG']}; color: {P['TOOLTIP_FG']}; border: 1px solid {P['ACCENT_DARK']};
           padding: 6px 8px; }}

QMenuBar {{ background: {P['BG_BAR']}; border-bottom: 1px solid {P['LINE_MID']}; padding: 1px 6px; }}
QMenuBar::item {{ padding: 5px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {P['BG_BTN']}; }}
QMenu {{ background: {P['BG_MENU']}; border: 1px solid {P['LINE_FIELD']}; padding: 4px 0; }}
QMenu::item {{ padding: 5px 28px 5px 18px; }}
QMenu::item:selected {{ background: {P['LINE_MID']}; }}
QMenu::item:disabled {{ color: {P['TEXT_FAINT']}; }}
QMenu::separator {{ height: 1px; background: {P['BG_BTN']}; margin: 4px 8px; }}

QPushButton {{ background: {P['BG_BTN']}; border: 1px solid {P['LINE_FIELD']}; color: {P['TEXT_BRIGHT']};
              padding: 6px 12px; font-weight: bold; letter-spacing: 1px; }}
QPushButton:hover {{ border-color: {P['ACCENT']}; }}
QPushButton:pressed {{ background: {P['LINE_MID']}; }}
QPushButton:disabled {{ background: {P['BG_BTN_OFF']}; color: {P['TEXT_FAINT']}; border-color: {P['LINE_DISABLED']}; }}
QPushButton#primary {{ background: {P['ACCENT']}; color: {P['TEXT_ON_ACCENT']}; border: none;
                      padding: 7px 22px; }}
QPushButton#primary:hover {{ background: {P['ACCENT_HOVER']}; }}
QPushButton#primary:disabled {{ background: {P['PRIMARY_OFF']}; color: {P['PRIMARY_OFF_TEXT']}; }}
QPushButton#secondary {{ background: {P['BTN2_BG']}; color: {P['BTN2_FG']}; border: none; padding: 7px 16px; }}
QPushButton#secondary:hover {{ background: {P['BTN2_HOVER']}; }}
QPushButton#secondary:disabled {{ background: {P['BTN2_OFF_BG']}; color: {P['TEXT_FAINT']}; }}
QPushButton#stop {{ background: {P['STOP_BG']}; color: {P['STOP_FG']}; border: 1px solid {P['RED']};
                   padding: 7px 22px; }}
QPushButton#stop:hover {{ background: {P['STOP_HOVER']}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {P['LINE_FIELD']}; color: {P['TEXT_DIM']};
                    padding: 2px 10px; font-size: 11px; font-weight: normal; letter-spacing: 0; }}
QPushButton#ghost:hover {{ color: {P['ACCENT_FG']}; border-color: {P['ACCENT_DARK']}; }}
QPushButton#tab {{ background: {P['BG_BAR']}; color: {P['TEXT_DIM']}; border: 1px solid {P['LINE']};
                  padding: 3px 10px; font-size: 11px; letter-spacing: 0; }}
QPushButton#tab:hover {{ color: {P['ACCENT_FG']}; }}
QPushButton#tab:checked {{ background: {P['ACCENT']}; color: {P['TEXT_ON_ACCENT']}; border-color: {P['ACCENT']}; }}
QPushButton#tab:disabled {{ color: {P['TEXT_FAINT']}; background: {P['BG_BAR']}; border-color: {P['LINE_DISABLED']}; }}
QPushButton#transport {{ background: transparent; border: none; color: {P['TEXT_DIM']};
                        padding: 2px 6px; font-size: 13px; letter-spacing: 0; }}
QPushButton#transport:hover {{ color: {P['ACCENT_FG']}; }}
QPushButton#swatch {{ border: 1px solid {P['LINE_FIELD']}; padding: 0; min-width: 44px; min-height: 22px; }}
QPushButton#swatch:hover {{ border-color: {P['ACCENT']}; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {P['BG_FIELD']}; border: 1px solid {P['LINE_FIELD']}; padding: 4px 8px;
    selection-background-color: {P['ACCENT']}; selection-color: {P['TEXT_ON_ACCENT']};
    min-height: 18px; }}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {P['ACCENT_DARK']}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {P['ACCENT']}; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {P['TEXT_FAINT']}; background: {P['BG_DISABLED']}; border-color: {P['LINE_DISABLED']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {P['BG_MENU']}; border: 1px solid {P['LINE_FIELD']};
    selection-background-color: {P['LINE_MID']}; selection-color: {P['TEXT_BRIGHT']}; outline: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border;
    subcontrol-position: top right; width: 18px; border: none; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border;
    subcontrol-position: bottom right; width: 18px; border: none; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 9px; height: 9px; }}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{ image: url({up_hi}); }}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{ image: url({down_hi}); }}

QSlider::groove:horizontal {{ height: 3px; background: {P['TEXT_FAINT']}; }}
QSlider::sub-page:horizontal {{ background: {P['TEXT_FAINT']}; }}
QSlider::handle:horizontal {{ background: {P['GREEN']}; width: 12px; height: 12px;
                             margin: -5px 0; border: none; }}
QSlider::handle:horizontal:hover {{ background: {P['GREEN_HOVER']}; }}
QSlider::handle:horizontal:disabled {{ background: {P['GREEN_OFF']}; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {P['TEXT_FAINT']}; background: {P['BG_FIELD']}; }}
QCheckBox::indicator:hover {{ border-color: {P['ACCENT_DARK']}; }}
QCheckBox::indicator:checked {{ background: {P['ACCENT']}; border: 1px solid {P['ACCENT']}; }}
QCheckBox::indicator:disabled {{ background: {P['BG_DISABLED']}; border-color: {P['LINE_DISABLED']}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {P['TEXT_FAINT']}; border-radius: 8px;
                          background: {P['BG_FIELD']}; }}
QRadioButton::indicator:hover {{ border-color: {P['ACCENT_DARK']}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                   stop:0 {P['ACCENT']}, stop:0.55 {P['ACCENT']}, stop:0.6 {P['BG_FIELD']}, stop:1 {P['BG_FIELD']});
                                   border: 1px solid {P['ACCENT']}; }}
QRadioButton::indicator:disabled {{ background: {P['BG_DISABLED']}; border-color: {P['LINE_DISABLED']}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {P['TEXT_FAINT']}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 9px; background: {P['BG_BAR']}; margin: 0; }}
QScrollBar::handle:vertical {{ background: {P['LINE_FIELD']}; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {P['ACCENT_DARK']}; }}
QScrollBar:horizontal {{ height: 9px; background: {P['BG_BAR']}; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {P['LINE_FIELD']}; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {P['ACCENT_DARK']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: 1px solid {P['LINE_MID']}; background: {P['BG_BAR']}; top: -1px; }}
QTabBar::tab {{ background: {P['BG_BAR']}; color: {P['TEXT_DIM']}; border: 1px solid {P['LINE']};
               padding: 6px 16px; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {P['TEXT_ON_ACCENT']}; background: {P['ACCENT']}; border-color: {P['ACCENT']}; }}
QTabBar::tab:hover:!selected {{ color: {P['ACCENT_FG']}; }}
QGroupBox {{ border: 1px solid {P['LINE_MID']}; margin-top: 10px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {P['TEXT_DIM']}; }}

QPlainTextEdit {{ background: {P['BG_CONSOLE']}; border: 1px solid {P['LINE_FIELD']}; }}
QDialog, QMessageBox {{ background: {P['BG_BAR']}; }}
QLabel#dim {{ color: {P['TEXT_DIM']}; }}
QFrame#hline {{ background: {P['LINE_MID']}; max-height: 1px; min-height: 1px; border: none; }}
"""


def apply_theme(app) -> None:
    f = QFont()
    f.setFamilies(FONT_STACK)
    f.setPixelSize(12)
    app.setFont(f)
    app.setStyleSheet(stylesheet())


def retheme(app, name: str, custom: Optional[dict] = None) -> None:
    """Switch the palette of a running application."""
    set_theme(name, custom)
    app.setStyleSheet(stylesheet())
    restyle_all()
    for w in app.allWidgets():
        w.update()


def style_box(w, name: str, bg: str, top: str = "", bottom: str = "", left: str = "",
              right: str = "") -> None:
    """Background/border for ONE container. A selector-less setStyleSheet would cascade
    into every child widget and override the global button/tab styles.
    Colours are palette keys (e.g. "BG_PANEL") so they follow theme changes."""
    w.setObjectName(name)
    w.setAttribute(Qt.WA_StyledBackground, True)

    def css() -> str:
        out = f"background:{c(bg)};"
        for side, col in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
            if col:
                out += f"border-{side}:1px solid {c(col)};"
        return f"QWidget#{name}{{{out}}}"
    sty(w, css)


def mono_font(px: int = 11) -> QFont:
    f = QFont()
    f.setFamilies(MONO_STACK)
    f.setPixelSize(px)
    f.setStyleHint(QFont.Monospace)
    return f
