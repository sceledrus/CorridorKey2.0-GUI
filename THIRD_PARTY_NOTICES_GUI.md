# Third-party notices

CorridorKey 2.0 itself is under the Corridor Key Licence 2.0 (see [LICENSE](LICENSE)). It uses the following
software. Each remains under its own licence; none of it is modified.

| Component | Used for | Licence | Where to get the source |
|---|---|---|---|
| **Qt 6 / Qt for Python (PySide6)** | the window | LGPL-3.0 (Qt libraries and the PySide6 bindings) | https://www.qt.io/qt-for-python and https://code.qt.io |
| **OpenCV** (`opencv-python`) | reading frames, GrabCut for the Subject Marker | Apache-2.0; the wheels also ship FFmpeg libraries under LGPL-2.1 | https://github.com/opencv/opencv-python |
| **NumPy** | image arrays, chime synthesis | BSD-3-Clause; the wheels also ship OpenBLAS (BSD-3-Clause) and libgfortran (GPL-3.0 with the GCC runtime library exception) | https://numpy.org |
| **PyInstaller** | *build time only*: freezes the standalone window. Its bootloader is part of the resulting exe. | GPL-2.0-or-later with an exception that allows it to be used for any program | https://pyinstaller.org |
| **Python** | runs the GUI; bundled in the standalone build | PSF License | https://www.python.org |
| **Pillow** | *build time only*: makes the exe's icon | HPND | https://python-pillow.org |
| **Zig** (`ziglang`) | *build time only*: C compiler used to build the small launcher exe | MIT | https://ziglang.org |

**LGPL note (Qt).** The standalone download is a *folder*, not a single packed file: the Qt libraries are separate files in
`ck2_runtime\PySide6\Qt\`, so you can replace them with your own build of the same Qt version. The window's own source code is in
this repository.

**CorridorKey 2.0** (the model, `infer.py`, and the weights) is by Corridor Digital and is **not** included here. It has its own
licence and its own third-party notices; get it from https://corridorkey.com.

This is not legal advice. If you redistribute a modified build, check each licence above yourself.
