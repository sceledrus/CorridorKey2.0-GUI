"""Control-flow tests for launcher.c compiled against the Linux shim (see README.txt)."""
import os, subprocess, sys, tempfile, textwrap
from pathlib import Path

HARNESS = Path(sys.argv[1]).resolve()
MARK = "# ck2-launcher:crash-report\n"
fails = 0

PY = textwrap.dedent('''\
    #!/bin/sh
    echo "python.exe $*" >> "$CK_TEST_LOG"
    S="%(s)s"
    if [ -f "$S/dead" ]; then echo "Fatal Python error: init_fs_encoding: failed to get the Python codec" >&2; exit 1; fi
    case "$*" in
      *"import PySide6.QtWidgets"*)
        case "$(cat "$S/pyside" 2>/dev/null || echo ok)" in
          ok) exit 0;;
          missing) echo "Traceback (most recent call last):" >&2; echo "ModuleNotFoundError: No module named 'PySide6'" >&2; exit 1;;
          broken) echo "ImportError: DLL load failed while importing QtWidgets: The specified module could not be found." >&2; exit 1;;
        esac;;
      *"import cv2, numpy"*)
        if [ "$(cat "$S/cv" 2>/dev/null || echo ok)" = missing ]; then echo "ModuleNotFoundError: No module named 'cv2'" >&2; exit 1; fi
        exit 0;;
      *"-m pip install"*)
        [ "${PIP_EXIT:-0}" = 0 ] && [ "${PIP_FIXES:-1}" = 1 ] && echo ok > "$S/pyside"
        exit ${PIP_EXIT:-0};;
    esac
    exit 0
''')
PYW = textwrap.dedent('''\
    #!/bin/sh
    echo "pythonw.exe argc=$#" >> "$CK_TEST_LOG"
    for a in "$@"; do echo "  arg=[$a]" >> "$CK_TEST_LOG"; done
    if [ -f "%(s)s/gui_exit" ]; then
      echo "Traceback (most recent call last):" >&2
      echo "ModuleNotFoundError: No module named 'PySide6'" >&2
      exit $(cat "%(s)s/gui_exit")
    fi
    sleep 6
''')


def mk_tree(venv=True, pythonw=True, script=True, marker=True):
    root = Path(tempfile.mkdtemp()) / "Corridor Key 2.0"        # a space in the folder name, like a real install
    root.mkdir(parents=True)
    if script:
        (root / "run_gui.py").write_text((MARK if marker else "") + "# stub\n")
    state = root / "state"; state.mkdir()
    if venv:
        sc = root / "venv" / "Scripts"; sc.mkdir(parents=True)
        (sc / "python.exe").write_text(PY % {"s": state}); os.chmod(sc / "python.exe", 0o755)
        if pythonw:
            (sc / "pythonw.exe").write_text(PYW % {"s": state}); os.chmod(sc / "pythonw.exe", 0o755)
    return root, state


def run(root, cmdline=None, answer="no", path="", **env_extra):
    log = root.parent / "log.txt"; log.write_text("")
    tmp = root.parent / "temp"; tmp.mkdir(exist_ok=True)
    env = dict(os.environ, CK_TEST_LOG=str(log), CK_TEST_EXE=str(root / "CorridorKey2.exe"), CK_TEST_TEMP=str(tmp),
               CK_TEST_CMDLINE=cmdline if cmdline is not None else '"C:\\x\\CorridorKey2.exe"',
               CK_TEST_ANSWER=answer, CK_TEST_PATH=path)
    env.update({k: str(v) for k, v in env_extra.items()})
    r = subprocess.run([str(HARNESS)], env=env, capture_output=True, text=True, timeout=30)
    return r.returncode, log.read_text()


def spawns(log):
    return [l for l in log.splitlines() if l.startswith("SPAWN")]


def probes(log, what):
    return sum(1 for l in spawns(log) if what in l)


def check(name, cond, detail=""):
    global fails
    print(("  ok  " if cond else "  FAIL") + " " + name + ("" if cond else f"\n      {detail}"))
    fails += 0 if cond else 1


def boxes(log):
    return [l for l in log.splitlines() if l.startswith("MSGBOX")]


print("1. missing run_gui.py")
root, _ = mk_tree(script=False); rc, log = run(root)
check("error box, exit 1, nothing spawned", rc == 1 and "run_gui.py was not found" in log and "SPAWN" not in log, log)

print("2. no python anywhere")
root, _ = mk_tree(venv=False); rc, log = run(root)
check("'Python was not found', exit 1", rc == 1 and "Python was not found" in log and "SPAWN" not in log, log)

print("3. only the Microsoft Store stub on PATH")
root, _ = mk_tree(venv=False); stub = root.parent / "Local" / "Microsoft" / "WindowsApps"; stub.mkdir(parents=True)
(stub / "python.exe").write_text("stub"); rc, log = run(root, path=str(stub))
check("stub rejected", rc == 1 and "Python was not found" in log, log)

print("4. venv fine, files dropped on the exe")
root, _ = mk_tree(); drop = '"C:\\x\\CorridorKey2.exe" "/tmp/my clips/shot one.mp4" /tmp/folder'
rc, log = run(root, cmdline=drop); sp = spawns(log)
check("exit 0, no message boxes", rc == 0 and not boxes(log), log)
check("two hidden checks (PySide6, then OpenCV/numpy) via -c, not via run_gui.py",
      len(sp) == 3 and all("flags=0x8000000" in l for l in sp[:2]) and "import PySide6.QtWidgets" in sp[0]
      and "import cv2, numpy" in sp[1] and "run_gui.py" not in sp[0] + sp[1], str(sp))
check("GUI started via pythonw with normal flags", "flags=0x0" in sp[2] and "pythonw.exe" in sp[2], str(sp))
check("script path with a space survived quoting", "arg=[" + str(root / "run_gui.py") + "]" in log, log)
check("dropped paths passed verbatim (space kept, 2 args)", "arg=[/tmp/my clips/shot one.mp4]" in log and "arg=[/tmp/folder]" in log and "argc=3" in log, log)

print("5. started with no arguments")
root, _ = mk_tree(); rc, log = run(root)
check("GUI gets only the script path (argc=1)", rc == 0 and "argc=1" in log, log)

print("6. PySide6 missing -> user says yes")
root, st = mk_tree(); (st / "pyside").write_text("missing"); rc, log = run(root, answer="yes")
check("asked, pip in a NEW console, re-checked, then OpenCV check and GUI",
      rc == 0 and "MSGBOX type=0x10024" in log and "-m pip install PySide6-Essentials" in log and "flags=0x10 " in log
      and probes(log, "import PySide6") == 2 and probes(log, "import cv2") == 1 and "pythonw.exe argc=" in log, log)

print("7. PySide6 missing -> user says no")
root, st = mk_tree(); (st / "pyside").write_text("missing"); rc, log = run(root, answer="no")
check("exit 1, no pip, no GUI", rc == 1 and "-m pip install" not in log and "pythonw.exe" not in log and probes(log, "import PySide6") == 1, log)

print("8. PySide6 missing, yes, but pip fails")
root, st = mk_tree(); (st / "pyside").write_text("missing"); rc, log = run(root, answer="yes", PIP_EXIT=1)
check("reports 'exit code 1', no GUI", rc == 1 and "did not finish (exit code 1)" in log and "pythonw.exe argc" not in log, log)

print("9. pip 'succeeds' but PySide6 still missing")
root, st = mk_tree(); (st / "pyside").write_text("missing"); rc, log = run(root, answer="yes", PIP_FIXES=0)
last = boxes(log)[-1] if boxes(log) else ""
check("bounded to two checks; dialog names python.exe and shows Python's error",
      rc == 1 and probes(log, "import PySide6") == 2 and "still cannot load it" in last and "venv\\Scripts\\python.exe" in last
      and "No module named 'PySide6'" in last and "(exit code 1)" in last, log)

print("10. PySide6 installed but broken (DLL error)")
root, st = mk_tree(); (st / "pyside").write_text("broken"); rc, log = run(root, answer="yes")
check("no install offer; the real error is shown",
      rc == 1 and "type=0x10024" not in log and "-m pip" not in log and "DLL load failed while importing QtWidgets" in log, log)

print("11. OpenCV / numpy missing")
root, st = mk_tree(); (st / "cv").write_text("missing"); rc, log = run(root)
check("shows Python's error and points at requirements.txt",
      rc == 1 and "No module named 'cv2'" in log and "requirements.txt" in log and "pythonw.exe" not in log, log)

print("12. Python itself is broken (this is the error from the screenshot: 'exit code 1' and no cause)")
root, st = mk_tree(); (st / "dead").write_text("1"); rc, log = run(root)
check("dialog includes Python's own message, exit 1, no GUI",
      rc == 1 and "Fatal Python error: init_fs_encoding" in log and "(exit code 1)" in log and "pythonw.exe" not in log, log)

print("13. GUI dies right away (run_gui.py has the crash-report marker)")
for code, expect_box in ((3, True), (1, False), (0, False)):
    root, st = mk_tree(); (st / "gui_exit").write_text(str(code)); rc, log = run(root)
    shown = "closed right after starting (exit code %d)" % code in log
    check(f"exit code {code}: {'explains, with output' if expect_box else 'silent'}",
          rc == 0 and shown == expect_box and (not expect_box or "No module named 'PySide6'" in log), log)

print("14. older run_gui.py without the marker (no crash reporting of its own)")
root, st = mk_tree(marker=False); (st / "gui_exit").write_text("1"); rc, log = run(root)
check("exit 1 is NOT silent: says run_gui.py is older and shows the output",
      rc == 0 and "closed right after starting (exit code 1)" in log and "older than this CorridorKey2.exe" in log
      and "No module named 'PySide6'" in log, log)
root, st = mk_tree(marker=False); rc, log = run(root)
check("environment check still passes with an older run_gui.py; GUI launched", rc == 0 and not boxes(log) and "pythonw.exe argc=" in log, log)
root, st = mk_tree(marker=False); (st / "pyside").write_text("missing"); rc, log = run(root, answer="yes")
check("older run_gui.py + PySide6 missing: install offered and the GUI then starts",
      rc == 0 and "type=0x10024" in log and "pythonw.exe argc=" in log, log)

print("15. GUI keeps running")
root, _ = mk_tree(); rc, log = run(root)
check("launcher returns 0 after ~4s without a message box", rc == 0 and not boxes(log), log)

print("16. venv without pythonw.exe")
root, _ = mk_tree(pythonw=False); rc, log = run(root)
check("falls back to python.exe with CREATE_NO_WINDOW", len(spawns(log)) == 3 and "flags=0x8000000" in spawns(log)[2], str(spawns(log)))

print("17. no venv, python on PATH")
root, _ = mk_tree(venv=False); bindir = root.parent / "pybin"; bindir.mkdir()
for n in ("python.exe", "pythonw.exe"):
    (bindir / n).write_text('#!/bin/sh\necho "%s $*" >> "$CK_TEST_LOG"\nexit 0\n' % n); os.chmod(bindir / n, 0o755)
rc, log = run(root, path=str(bindir))
check("PATH python for the checks, its pythonw for the GUI, no doubled backslash",
      rc == 0 and log.count(str(bindir).replace("/", "\\")) >= 3 and "\\\\pythonw.exe" not in log and "pybin\\pythonw.exe" in log, log)

print("18. .venv is found when venv is absent")
root, _ = mk_tree(venv=False); sc = root / ".venv" / "Scripts"; sc.mkdir(parents=True)
for n in ("python.exe", "pythonw.exe"):
    (sc / n).write_text("#!/bin/sh\necho %s $* >> $CK_TEST_LOG\nexit 0\n" % n); os.chmod(sc / n, 0o755)
rc, log = run(root); check(".venv used", rc == 0 and "\\.venv\\Scripts\\pythonw.exe" in log, log)

print(f"\n{'ALL LAUNCHER CASES PASSED' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
