#!/usr/bin/env python3
"""Rebuild CorridorKey2.exe from launcher.c. Works on Windows, Linux or macOS.

    pip install ziglang pillow
    python launcher/build.py

zig bundles a C compiler and the Windows headers, so no Visual Studio is needed.
"""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "CorridorKey2.exe"


def _subsystem(path: Path) -> int:
    d = path.read_bytes()
    pe = int.from_bytes(d[0x3C:0x40], "little")
    return int.from_bytes(d[pe + 24 + 68:pe + 24 + 70], "little")     # optional header + 68 (PE32+)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.check_call([sys.executable, str(HERE / "make_icon.py"), str(tmp / "ck2.ico"), str(ROOT / "ck2_gui" / "icon.png")])
        for f in ("launcher.c", "launcher.rc", "ck2.manifest"):
            (tmp / f).write_bytes((HERE / f).read_bytes())
        subprocess.check_call([
            sys.executable, "-m", "ziglang", "cc", "-target", "x86_64-windows-gnu", "-Os", "-s", "-Wl,--subsystem,windows",
            "-Wall", "-Wextra", "-o", str(OUT), "launcher.c", "launcher.rc"], cwd=tmp)
    sub = _subsystem(OUT)
    if sub != 2:                                   # 2 = WINDOWS_GUI, 3 = console (would flash a black window)
        raise SystemExit(f"build error: {OUT.name} has PE subsystem {sub}, expected 2 (GUI)")
    print(f"built {OUT}  ({OUT.stat().st_size:,} bytes)\nsha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
