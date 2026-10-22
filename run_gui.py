#!/usr/bin/env python3
# ck2-launcher:crash-report  (CorridorKey2.exe looks for this line: this script reports its own startup errors)
"""CorridorKey 2.0 - desktop GUI for CorridorKey 2.0 (Corridor Digital).

    python run_gui.py                 # empty window, drop clips on it
    python run_gui.py shot.mp4 ...    # import clips / frame folders on launch
    python run_gui.py --check         # exit code 0 ok, 11 PySide6 missing, 12 OpenCV/numpy missing
    python run_gui.py --selftest      # build the window off-screen, exercise it, exit 0 if healthy

The GUI is a front-end for infer.py: it never loads the model itself.

When started through CorridorKey2.exe (launcher, or the standalone build from build_exe.bat) there is no
console, so errors are written to a crash log and shown in a dialog instead of vanishing.
"""
import os
import sys
import traceback

_shown_dialog = False


def _log_path():
    try:
        from ck2_gui.model import config_dir
        return config_dir() / "crash.log"
    except Exception:
        return None


def _report(title: str, text: str, dialog: bool = True) -> None:
    """Append to crash.log and (once per session) tell the user where it is."""
    global _shown_dialog
    log = _log_path()
    if log is not None:
        try:
            try:
                from ck2_gui.model import scrub
                clean = scrub(text)         # crash.log never contains your Windows user name, so it is safe to attach
            except Exception:
                clean = text
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"--- {title} ---\n{clean}\n")
        except OSError:
            log = None
    if sys.stderr is not None:
        try:
            print(text, file=sys.stderr)
        except Exception:
            pass
    if not dialog or _shown_dialog or os.name != "nt":
        return
    _shown_dialog = True
    msg = text.strip()[-1200:]
    if log is not None:
        msg += f"\n\nFull details were saved to:\n{log}"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)   # MB_ICONERROR
    except Exception:
        pass


def _excepthook(etype, value, tb):
    _report("CorridorKey 2.0 - unexpected error",
            "".join(traceback.format_exception(etype, value, tb)))


def check_env() -> int:
    """Used by CorridorKey2.exe before launching: 0 ok, 11 PySide6 missing, 12 OpenCV/numpy missing."""
    for mod, code in (("PySide6.QtWidgets", 11), ("cv2", 12), ("numpy", 12)):   # PySide6 before cv2
        try:
            __import__(mod)
        except Exception:
            return code
    return 0


def _bundle_dir():
    """Folder holding ck2_gui/icon.png: next to this file, or the PyInstaller bundle."""
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))


def selftest() -> int:
    """Off-screen smoke test used to validate a frozen build: window builds, themes switch, help text and
    the sound/marker engines load. Writes the verdict to config_dir()/selftest.txt and returns 0 if healthy."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines, code = [], 0
    try:
        from PySide6.QtWidgets import QApplication
        import cv2
        import numpy as np
        from ck2_gui import APP_NAME, __version__, sound, subject, theme
        from ck2_gui.main_window import MainWindow
        from ck2_gui.model import FROZEN, REPO_ROOT, config_dir

        app = QApplication([])
        theme.apply_theme(app)
        win = MainWindow(restore=False)
        win.show()
        app.processEvents()
        lines.append(f"{APP_NAME} {__version__} frozen={FROZEN} repo_root={REPO_ROOT}")
        assert win.windowTitle() == APP_NAME, win.windowTitle()
        for name in ("light", "custom", "dark"):
            theme.retheme(app, name, {"bg": "#202830", "panel": "#2a3440", "text": "#e8eef4",
                                      "accent": "#ff8a3d", "ok": "#3dd68c", "danger": "#ff5c5c"})
            app.processEvents()
        lines.append("themes ok")
        assert win.params.hint_mode.itemData(1) == "marker"
        assert win.params._sections[0].head.toolTip(), "section tooltips missing"
        lines.append("help text ok")
        img = np.zeros((120, 160, 3), np.uint8)
        img[:] = (20, 200, 40)
        cv2.circle(img, (80, 60), 30, (200, 150, 120), -1)
        res = subject.segment_subject(img, [(0.5, 0.5, 1)])
        assert res.coverage > 0.05, res.coverage
        lines.append(f"subject marker ok ({res.coverage:.2f})")
        wav = sound.SoundPlayer(str(config_dir() / "sounds"), backend=lambda p: True).chime_path("sparkle")
        assert os.path.exists(wav)
        lines.append("sound ok")
        win.close()
    except BaseException:
        code = 1
        lines.append(traceback.format_exc())
    try:
        from ck2_gui.model import config_dir
        (config_dir() / "selftest.txt").write_text("\n".join(lines) + f"\nexit={code}\n", encoding="utf-8")
    except Exception:
        pass
    print("\n".join(lines), file=sys.stderr if sys.stderr else None)
    return code


def main(argv):
    # PySide6 must be imported before OpenCV (see ck2_gui/sources.py).
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from ck2_gui import APP_NAME, theme
    from ck2_gui.main_window import MainWindow

    if os.name == "nt":
        try:   # own taskbar identity/icon instead of being grouped under python
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CorridorKey.GUI.2")
        except Exception:
            pass
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    icon = os.path.join(_bundle_dir(), "ck2_gui", "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    theme.apply_theme(app)
    win = MainWindow()
    win.show()
    paths = [a for a in argv[1:] if not a.startswith("-")]
    if paths:
        win.import_paths(paths)
    return app.exec()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if "--check" in sys.argv:
        sys.exit(check_env())
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.excepthook = _excepthook
    try:
        code = main(sys.argv)
    except SystemExit:
        raise
    except BaseException:
        _report("CorridorKey 2.0 could not start", traceback.format_exc())
        code = 1
    sys.exit(code)
