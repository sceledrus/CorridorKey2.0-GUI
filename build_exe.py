#!/usr/bin/env python3
"""Build the standalone CorridorKey 2.0 window as a real native program (no Python needed to open it).

    python build_exe.py                 # -> dist/CorridorKey2/CorridorKey2.exe   (folder build, starts fastest)
    python build_exe.py --onefile       # -> dist/CorridorKey2.exe                  (single file, slower first start)
    python build_exe.py --no-venv       # build with the Python you are running instead of a fresh build environment
    python build_exe.py --selftest      # after building, start the result off-screen once and check it is healthy

What this makes - and what it cannot
  The window is frozen with PyInstaller together with PySide6, OpenCV and numpy, so it starts like any other Windows
  program. The AI model itself (PyTorch + CUDA + weights, several GB) cannot be frozen into a small exe, so the program
  still starts `infer.py` with the Python from your CorridorKey `venv` for each run. That is why the exe must stay inside
  (up to three folders below) your CorridorKey folder - the one that holds infer.py, weights/ and venv/.

Run this on the OS you want the exe for: PyInstaller cannot cross-compile, so the Windows exe has to be built on Windows
(build_exe.bat does exactly that). Needs Python 3.10-3.12 and internet access for pip.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = Path(os.environ.get("CK2_BUILD_DIR") or ROOT / "build_gui")      # scratch folder (safe to delete)
NAME = "CorridorKey2"
IS_WIN = os.name == "nt"

# The GUI only needs these. (The model's own requirements stay in the CorridorKey venv.)
PySide = "PySide6-Essentials>=6.6"
EXCLUDES = ["tkinter", "matplotlib", "scipy", "pandas", "torch", "torchvision", "IPython", "pytest", "PIL.ImageTk"]
# The window only uses QtCore / QtGui / QtWidgets. Leaving the other Qt modules out makes the download much smaller and
# - for QtNetwork - guarantees the bundled program contains no Qt networking or TLS code at all.
EXCLUDES += ["PySide6." + m for m in (
    "QtNetwork", "QtDBus", "QtOpenGL", "QtOpenGLWidgets", "QtQml", "QtQuick", "QtQuickWidgets", "QtQuickControls2",
    "QtPdf", "QtPdfWidgets", "QtSvg", "QtSvgWidgets", "QtSql", "QtXml", "QtTest", "QtPrintSupport", "QtConcurrent",
    "QtHelp", "QtDesigner", "QtUiTools", "QtMultimedia", "QtWebChannel", "QtWebSockets", "Qt3DCore")]


def sh(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call([str(c) for c in cmd], **kw)


def req_line(prefix: str, fallback: str) -> str:
    """Take numpy / opencv pins from the repo's requirements.txt so the exe uses the same versions as the model's env."""
    try:
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            if re.match(rf"^{re.escape(prefix)}\b", line.strip(), re.I):
                return line.split("#")[0].strip()
    except OSError:
        pass
    return fallback


def build_python(no_venv: bool) -> Path:
    if no_venv:
        return Path(sys.executable)
    env = BUILD / "venv"
    print(f"Creating an isolated build environment in {env} ...", flush=True)
    venv.EnvBuilder(with_pip=True, clear=True).create(env)
    return env / ("Scripts/python.exe" if IS_WIN else "bin/python")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onefile", action="store_true", help="single exe instead of a folder")
    ap.add_argument("--no-venv", action="store_true", help="use the current Python environment as it is")
    ap.add_argument("--selftest", action="store_true", help="run the built program's --selftest afterwards")
    ap.add_argument("--dist", default=str(ROOT / "dist"), help="output folder (default: ./dist)")
    a = ap.parse_args()
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is needed to build.")
        return 2
    if not (ROOT / "run_gui.py").exists():
        print("Run this from the CorridorKey folder (run_gui.py not found next to build_exe.py).")
        return 2
    BUILD.mkdir(exist_ok=True)

    py = build_python(a.no_venv)
    if not a.no_venv:
        sh([py, "-m", "pip", "install", "--upgrade", "pip"])
        sh([py, "-m", "pip", "install", PySide, req_line("opencv-python", "opencv-python>=4.11"),
            req_line("numpy", "numpy>=1.26,<2"), "pillow", "pyinstaller>=6.6"])

    ico = BUILD / "ck2.ico"
    sh([py, ROOT / "launcher" / "make_icon.py", ico, ROOT / "ck2_gui" / "icon.png"])

    cmd = [py, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", NAME,
           "--distpath", a.dist, "--workpath", BUILD / "work", "--specpath", BUILD,
           "--windowed", "--icon", ico,
           "--add-data", f"{ROOT / 'ck2_gui' / 'icon.png'}{os.pathsep}ck2_gui",
           "--collect-submodules", "ck2_gui"]
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]
    cmd += ["--onefile"] if a.onefile else ["--contents-directory", "ck2_runtime"]
    cmd += [ROOT / "run_gui.py"]
    sh(cmd, cwd=ROOT)

    dist = Path(a.dist)
    leaf = NAME + (".exe" if IS_WIN else "")
    exe = dist / leaf if a.onefile else dist / NAME / leaf
    if not exe.exists():
        print(f"Build finished but {exe} is missing - check the PyInstaller output above.")
        return 1
    size = exe.stat().st_size
    print(f"\nBuilt {exe}  ({size / 1e6:.1f} MB{'' if a.onefile else ' for the exe; the folder next to it holds the runtime'})")
    print("sha256", hashlib.sha256(exe.read_bytes()).hexdigest())
    if a.selftest:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen" if not IS_WIN else os.environ.get("QT_QPA_PLATFORM", ""))
        if not IS_WIN:
            env.setdefault("XDG_CONFIG_HOME", str(BUILD / "cfg"))
        r = subprocess.run([str(exe), "--selftest"], env=env, timeout=300)
        print("selftest exit code", r.returncode)
        if r.returncode:
            return r.returncode
    here = exe.parent.resolve()
    inside = any((p / "infer.py").exists() for p in (here, *list(here.parents)[:3]))
    print("\nNext: double-click the exe." if inside else
          "\nNote: this folder is not inside your CorridorKey folder - move it there, or set infer.py and Python in Settings > General.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
