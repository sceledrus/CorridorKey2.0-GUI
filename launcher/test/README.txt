Linux-only check of launcher.c's control flow (no Windows needed):

    gcc -Wall -Wextra -Ilauncher/test -o /tmp/ck2_harness launcher/launcher.c launcher/test/shim.c
    python3 launcher/test/run_cases.py /tmp/ck2_harness

launcher.c is compiled unchanged against a tiny Win32 shim (shim.c / windows.h) that maps CreateProcessW,
MessageBoxW, SearchPathW etc. onto fork/exec and a log file. 15 scenarios use fake python.exe / pythonw.exe
scripts: missing run_gui.py, no Python, Store stub, dropped files with spaces, PySide6 install yes/no/fail,
OpenCV missing, GUI exiting early, venv without pythonw, PATH python, .venv.
It proves the logic, not Windows behaviour (SmartScreen, real CreateProcess quirks, DLL loading).
