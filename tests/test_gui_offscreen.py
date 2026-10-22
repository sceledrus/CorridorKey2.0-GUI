"""Headless GUI test. Runs the real MainWindow offscreen against tests/fake_infer.py (a stand-in that
prints the same progress lines as corridorkey.runtime), so no GPU or model weights are needed.

    python tests/test_gui_offscreen.py [screenshot_dir]
"""
import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()          # never touch a real session file
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"                # must be set before cv2 is imported (OpenCV 5)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402  (PySide6 before cv2)
import numpy as np, cv2  # noqa: E402

from ck2_gui import theme  # noqa: E402
from ck2_gui.main_window import MainWindow  # noqa: E402
from ck2_gui.model import (build_command, default_output_dir, discover_outputs,  # noqa: E402
                           load_session, save_session)

work = Path(tempfile.mkdtemp(prefix="ck2gui_"))
shots = Path(sys.argv[1]) if len(sys.argv) > 1 else work / "screens"
shots.mkdir(parents=True, exist_ok=True)

# ---- synthetic footage: soft ellipse on a green plate, FrameHint companion, linear EXR sequence + AlphaHint
W, H, N = 640, 360, 48
vw = cv2.VideoWriter(str(work / "shot01.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, H))
mattes = []
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
for i in range(N):
    d = ((xx - (200 + i * 5)) / 110) ** 2 + ((yy - (180 + 30 * np.sin(i / 6))) / 140) ** 2
    a = np.clip((1.05 - d) * 6, 0, 1)
    img = np.array((0.35, 0.45, 0.85), np.float32) * a[..., None] + np.array((0.15, 0.75, 0.2), np.float32) * (1 - a[..., None])
    vw.write((img * 255).astype(np.uint8)); mattes.append(a)
vw.release()
cv2.imwrite(str(work / "shot01FrameHint.png"), (mattes[0] * 255).astype(np.uint8))
(work / "seq" / "Input").mkdir(parents=True); (work / "seq" / "AlphaHint").mkdir()
HAVE_EXR = cv2.haveImageWriter("x.exr")          # some OpenCV wheels (e.g. 5.0) are built without OpenEXR
if not HAVE_EXR:
    print("  note: this OpenCV has no OpenEXR; using a PNG plate sequence instead")
for i in range(6):
    if HAVE_EXR:
        cv2.imwrite(str(work / "seq" / "Input" / f"plate_{i:04d}.exr"), np.random.rand(H, W, 3).astype(np.float32) * 2)
    else:
        cv2.imwrite(str(work / "seq" / "Input" / f"plate_{i:04d}.png"), (np.random.rand(H, W, 3) * 255).astype(np.uint8))
    cv2.imwrite(str(work / "seq" / "AlphaHint" / f"hint_{i:04d}.png"), (mattes[i] * 255).astype(np.uint8))

app = QApplication([]); theme.apply_theme(app)
win = MainWindow(restore=False, infer_script=str(HERE / "fake_infer.py")); win.resize(1500, 812); win.show()


def wait(cond, timeout=40):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        app.processEvents(); time.sleep(0.01)
    return cond()


def shot(name):
    app.processEvents(); win.grab().save(str(shots / f"{name}.png"))


def ok(msg):
    print("  ok:", msg)


# ---------------------------------------------------------------- import + discovery
shot("01_welcome")
win.import_paths([str(work / "shot01.mp4"), str(work / "seq")]); wait(lambda: False, 0.3)
c0, c1 = win.clips
assert (c0.kind, c0.frames, c0.settings.hint_mode) == ("video", 48, "first"); ok("video imported, FrameHint auto-detected")
assert (c1.kind, c1.frames, c1.settings.hint_mode, c1.settings.frame_linear) == ("sequence", 6, "video", HAVE_EXR)
ok("frame sequence imported: AlphaHint dir detected" + (", EXR input defaults to linear" if HAVE_EXR else ""))
win.import_paths([str(work / "shot01.mp4")]); assert len(win.clips) == 2; ok("re-importing the same clip is ignored")

# ---------------------------------------------------------------- parameter panel -> Settings -> command
win.select_clip(c0.id); P = win.params; s = c0.settings
P.profile.setCurrentIndex(1); assert s.auto_vram is False
P.hann.setCurrentIndex(3); assert (s.hann_chunk, s.hann_stride) == (8, 4); ok("Manual memory + Hann preset 8/4")
P.low_vram.setChecked(True); P.temp.setText("/big/tmp"); P.temp.editingFinished.emit(); assert s.low_vram and s.temp_dir == "/big/tmp"
P.limit.setValue(12); P.start.setCurrentIndex(2); P.seed.setValue(5); assert (s.num_frames, s.start_mode, s.seed) == (12, "random_middle", 5)
P.out_checks["checker"].setChecked(False); assert s.outputs == ["alpha", "fg", "cutout"]
P.fmt.setCurrentIndex(1); assert s.output_format == "exr" and not P.codec.isEnabled() and P.exr_dtype.isEnabled(); ok("EXR format disables video-encoding controls")
P.fmt.setCurrentIndex(0); P.despill.setValue(75); P.hq.setValue(80); assert (s.despill, s.hint_quality) == (0.75, 0.8)
cmd = build_command("python", "infer.py", c0, "/o")
for flag in ("--low_vram", "--hann_chunk", "--hann_stride", "--num_frames", "--seed", "--despill_strength"):
    assert flag in cmd, flag
assert cmd[cmd.index("--outputs") + 1: cmd.index("--despill_strength")] == ["alpha", "fg", "cutout"]
ok("panel state -> infer.py command line")
P.profile.setCurrentIndex(0); P.limit.setValue(0); P.low_vram.setChecked(False); P.temp.setText(""); P.temp.editingFinished.emit()
P.out_checks["checker"].setChecked(True); P.hq.setValue(95); P.despill.setValue(50)
s.hann_chunk, s.hann_stride = 48, 24
win.select_clip(c1.id); assert P.space.isEnabled() and P.space.currentData() is HAVE_EXR and P.hint_mode.currentData() == "video"
win.select_clip(c0.id); assert not P.space.isEnabled(); ok("sequence-only controls follow the selected clip")

# ---------------------------------------------------------------- run, progress, outputs
events = []; win.runner.jobProgress.connect(lambda j: events.append((j.parser.phase, j.parser.frame, round(j.parser.fraction, 2))))
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"), (c0.status, c0.message)
assert events[-1] == ("DONE", 48, 1.0) and any(e[0] == "KEYING" for e in events); ok(f"job ran, progress parsed ({len(events)} updates)")
assert set(discover_outputs(default_output_dir(c0), c0.name)) == {"alpha", "fg", "checker", "cutout"}; wait(lambda: False, 0.3)
assert win.media.has_outputs() and win.viewer.mode == "checker"; ok("outputs discovered, viewer jumped to COMP")
shot("02_complete_comp")
for m in ("fg", "alpha", "cutout"):
    win.viewer.set_mode(m); assert win.viewer.right_view._img is not None, m
win.viewer.set_mode("cutout"); win.viewer.toggle_wipe(); win.viewer.right_view.wipe_pos = 0.45; win.viewer.refresh(); shot("03_wipe"); win.viewer.toggle_wipe()
ok("FG / MATTE / PROC views and A/B wipe render")

# ---------------------------------------------------------------- partial range maps outputs onto input frames
win._skip_overwrite_prompt = True
c0.settings.num_frames, c0.settings.start_mode = 10, "middle"; win.params.set_settings(c0.settings, c0.kind)
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"); wait(lambda: False, 0.3)
assert c0.ran_start == 19 and win.media.outputs["alpha"].count == 10
win.scrub.go(5); win.viewer.set_mode("alpha"); assert "OUTSIDE" in win.viewer.right_view.message
win.scrub.go(22); assert win.viewer.right_view.message == ""; shot("04_partial_range"); ok("partial run: outputs line up with input frames 19-28")
c0.settings.num_frames = 0

# ---------------------------------------------------------------- failure / cancel / busy-guard
os.environ["FAKE_FAIL"] = "1"; win.run_clips([c0]); assert wait(lambda: c0.status == "ERROR") and "out of memory" in c0.message; del os.environ["FAKE_FAIL"]
ok("failed job reports the real error line")
os.environ["FAKE_DELAY"] = "2"; win.run_clips([c0]); assert wait(lambda: c0.status == "RUNNING"); wait(lambda: False, 1.0)
assert win.viewer.mode == "input" and not win.media.has_outputs(); ok("half-written outputs are not opened while a clip is running")
win.stop(); assert wait(lambda: c0.status == "CANCELLED"); del os.environ["FAKE_DELAY"]; ok("Stop cancels the subprocess")
win.run_clips([c0, c0]); assert len([j for j in win.runner.jobs if j.status in ("QUEUED", "RUNNING")]) == 1; win.stop(); wait(lambda: not win.runner.is_busy())
ok("a clip cannot be queued twice")

# ---------------------------------------------------------------- session round trip
f = Path(tempfile.mkdtemp()) / "session.json"; save_session(win.clips, {"out_dir": "/x"}, f)
clips, prefs = load_session(f)
assert [c.name for c in clips] == ["shot01", "seq"] and prefs["out_dir"] == "/x" and clips[0].settings.hint_mode == "first"
ok("session save/load round trip")
shot("05_final"); print("ALL GUI TESTS PASSED  (screenshots:", shots, ")")
