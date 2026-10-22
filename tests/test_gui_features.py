"""Headless test of the features added in CorridorKey 2.0: rename, themes + settings dialog, hover help,
completion sound, subject marker, extra encoding controls, Nuke / After Effects export.

Runs the real MainWindow offscreen against tests/fake_infer.py (no GPU, no weights).

    python tests/test_gui_features.py [screenshot_dir]
"""
import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()          # never touch a real session file
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402  (PySide6 before cv2)
import numpy as np, cv2  # noqa: E402

from ck2_gui import APP_NAME, help_text as H, sound as SND, subject, theme  # noqa: E402
from ck2_gui.main_window import MainWindow  # noqa: E402
from ck2_gui.model import build_command, load_session, save_session, validate  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="ck2feat_"))
shots = Path(sys.argv[1]) if len(sys.argv) > 1 else work / "screens"
shots.mkdir(parents=True, exist_ok=True)

# ---- synthetic footage: two subjects on a green screen. A (orange) walks, B (blue) stands still.
W, Hh, N = 640, 360, 24
def make_video(name):
    vw = cv2.VideoWriter(str(work / name), cv2.VideoWriter_fourcc(*"mp4v"), 24, (W, Hh))
    for i in range(N):
        img = np.zeros((Hh, W, 3), np.uint8); img[:] = (40, 200, 40)                     # BGR green screen
        cv2.ellipse(img, (190 + i * 3, 190), (80, 130), 0, 0, 360, (110, 150, 220), -1)   # A
        cv2.ellipse(img, (500, 210), (60, 100), 0, 0, 360, (220, 80, 60), -1)             # B
        vw.write(img)
    vw.release()
make_video("shot01.mp4"); make_video("shot02.mp4")
A_XY, B_XY = (190, 190), (500, 210)                                                      # frame 0 centres (px)
(work / "seq" / "Input").mkdir(parents=True)
for i in range(4):
    cv2.imwrite(str(work / "seq" / "Input" / f"plate_{i:04d}.png"), (np.random.rand(Hh, W, 3) * 255).astype(np.uint8))

app = QApplication([]); theme.apply_theme(app)
win = MainWindow(restore=False, infer_script=str(HERE / "fake_infer.py")); win.resize(1500, 812); win.show()
played = []
win.sound.backend = lambda p: played.append(p) or True        # never make a real noise in a test


def wait(cond, timeout=40):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        app.processEvents(); time.sleep(0.01)
    return cond()


def shot(name):
    app.processEvents(); win.grab().save(str(shots / f"{name}.png"))


def ok(msg):
    print("  ok:", msg)


# ================================================================== rename
assert win.windowTitle() == "CorridorKey 2.0" == APP_NAME; ok("window title is CorridorKey 2.0")
win.import_paths([str(work / "shot01.mp4"), str(work / "shot02.mp4"), str(work / "seq")]); wait(lambda: False, 0.3)
c0, c1, c2 = win.clips
win.select_clip(c0.id); P = win.params; s = c0.settings
shot("10_welcome_imported")

# ================================================================== hover help
for sec in P._sections:
    tip = sec.head.toolTip()
    assert tip and sec.title.upper() in tip.upper() and "README" in tip, sec.title
    assert sec.title in H.SECTIONS, sec.title
ok(f"all {len(P._sections)} section headers explain themselves (with README pointers)")
missing = [k for sec in H.SECTIONS.values() for k in sec["params"] if k not in H.HELP]
assert not missing, missing
unhelped = [w.objectName() or type(w).__name__ for w, key in P._keys.items()
            if not key.startswith("ui:") and not w.toolTip()]
assert not unhelped, unhelped
used = {k for k in P._keys.values() if not k.startswith("ui:")}
for sec in H.SECTIONS.values():
    for k in sec["params"]:
        if k in ("out_alpha", "out_fg", "out_checker", "out_cutout"):
            continue
        assert k in used, f"help text '{k}' is not attached to any control"
ok(f"every control has a tooltip; every documented setting is attached to a control ({len(used)} help keys in use)")
for w in (win.brand.settings, win.status.run, win.status.run_all, win.scrub.bar, win.scrub.zoom, win.viewer.tabs["hint"], win.tray.in_label):
    assert w.toolTip(), w
ok("rest of the window (brand bar, run buttons, timeline, tabs, tray) has tooltips")
# no fixed help box any more: explanations live in tooltips next to the mouse
assert not any(hasattr(P, n) for n in ("strip", "strip_box", "strip_scroll")), "the bottom-right help box is gone"
from PySide6.QtCore import QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QToolTip
def hover(widget):
    """Send the same ToolTip event Qt sends when the mouse rests on a widget; return the text Qt then shows."""
    QToolTip.hideText()
    gp = widget.mapToGlobal(QPoint(4, 4))
    app.sendEvent(widget, QHelpEvent(QEvent.ToolTip, QPoint(4, 4), gp))
    app.processEvents()
    return widget.toolTip(), QToolTip.isVisible(), QToolTip.text()
tip, vis, shown = hover(P.hq)
assert "Hint quality" in tip and "Right now" in tip and "0.95" in tip, tip
P.hq.setValue(60); tip, vis, shown = hover(P.hq)
assert "low trust" in tip and "0.60" in tip and "0.95" not in tip.split("Right now")[1], tip
if vis:
    assert "low trust" in shown
P.hq.setValue(95)
ok("hovering a setting shows its explanation next to the mouse, and 'Right now' follows the current value")
for k in ("hint_quality", "carry_quality", "despill", "crf", "hann", "limit", "hint_mode", "marker_grow",
          "marker_soft", "fmt", "profile", "rate_mode", "bitrate", "pix_fmt", "threads", "model_scale"):
    v = {"hint_mode": "marker", "marker_grow": 5, "marker_soft": 8, "fmt": "exr", "profile": True,
         "rate_mode": "bitrate", "bitrate": "50M", "pix_fmt": "yuv420p", "threads": 2, "hann": (48, 24),
         "limit": 10, "crf": 12, "despill": 0.5, "hint_quality": 0.75, "carry_quality": 0.95, "model_scale": 0.5}[k]
    assert H.dynamic(k, v), k
ok("'Right now' sentences exist for every value-type control")

# ================================================================== themes + settings dialog
def pal_ok(name, custom=None):
    p = theme.palette_for(name, custom)
    for fg, bg, need in (("TEXT", "BG_ROOT", 4.5), ("TEXT", "BG_PANEL", 4.5), ("ACCENT_FG", "BG_ROOT", 3.0),
                         ("TOOLTIP_FG", "TOOLTIP_BG", 4.5), ("TEXT_DIM", "BG_PANEL", 3.0)):
        assert theme.contrast(p[fg], p[bg]) >= need, (name, fg, bg, theme.contrast(p[fg], p[bg]))
for n in ("dark", "light", "custom"):
    pal_ok(n)
ok("dark / light / default-custom palettes keep text readable (WCAG contrast)")

win.prefs["theme"] = "light"; win._apply_prefs()
assert theme.CURRENT == "light" and theme.LIGHT["BG_ROOT"] in app.styleSheet()
assert theme.LIGHT["BG_PANEL"] in P.styleSheet()
shot("11_theme_light"); ok("switching to the white theme re-styles the running window (stylesheet + inline styles)")
win.prefs["theme"] = "dark"; win._apply_prefs(); assert theme.DARK["BG_PANEL"] in P.styleSheet()

d = win.make_settings_dialog()
d.show(); app.processEvents()
assert d.theme_name == "dark" and not d.custom_box.isEnabled()
d.theme_radio["light"].setChecked(True); assert theme.CURRENT == "light"
d.theme_radio["custom"].setChecked(True); assert d.custom_box.isEnabled() and theme.CURRENT == "custom"
d.rows["accent"].set_value("#ff6600"); d.rows["accent"].changed.emit("accent", "#ff6600")
d.rows["bg"].set_value("#101820"); d.rows["bg"].changed.emit("bg", "#101820")
assert theme.CURRENT == "custom" and theme.ACCENT == "#ff6600" and theme.BG_ROOT == "#101820"
d.tabs.setCurrentIndex(1); shot("12_settings_appearance_custom"); app.processEvents(); d.grab().save(str(shots / "12b_dialog_appearance.png"))
d.rows["text"].set_value("#202020"); d.rows["text"].changed.emit("text", "#202020")
assert "hard to read" in d.read_note.text(); ok("custom theme maker previews live and warns about unreadable text")
d.start_from.setCurrentIndex(1); d._start_from(1); assert d.rows["bg"].value() == theme.CUSTOM_BASES["light"]["bg"]
d.rows["accent"].set_value("#ff6600"); d.rows["accent"].changed.emit("accent", "#ff6600")
d.rows["text"].set_value("#1a1a1a"); d.rows["text"].changed.emit("text", "#1a1a1a")
colors = d.custom_colors()
pal_ok("custom", colors); ok("a custom palette derived from six colours stays readable")
tf = work / "mytheme.json"; d.export_theme(str(tf))
d.theme_radio["dark"].setChecked(True); d.rows["bg"].set_value("#000000")
d.import_theme(str(tf)); assert d.custom_colors() == colors and d.theme_name == "custom"
bad = work / "bad.json"; bad.write_text("{\"hello\": 1}")
try:
    d.import_theme(str(bad)); raise AssertionError("bad theme accepted")
except ValueError:
    pass
bad.write_text("not json")
try:
    d.import_theme(str(bad)); raise AssertionError("garbage accepted")
except ValueError:
    pass
ok("theme export / import round-trips and rejects junk files")
d.reject(); win._apply_prefs()
assert theme.CURRENT == "dark" and win.prefs["theme"] == "dark"; ok("Cancel undoes the live theme preview")

holder = []
orig_make = win.make_settings_dialog
def spy():
    dd = orig_make(); holder.append(dd); return dd
win.make_settings_dialog = spy
def pick_custom_and_ok():
    dd = holder[0]; dd.theme_radio["custom"].setChecked(True)
    dd.rows["accent"].set_value("#22ccaa"); dd.rows["accent"].changed.emit("accent", "#22ccaa")
    dd.accept()
QTimer.singleShot(150, pick_custom_and_ok)
win.open_settings()
assert win.prefs["theme"] == "custom" and win.prefs["custom_theme"]["accent"] == "#22ccaa" and theme.ACCENT == "#22ccaa"
shot("13_theme_custom_applied"); ok("OK applies the custom theme to the whole window")
f = Path(tempfile.mkdtemp()) / "s.json"; save_session([], win.prefs, f)
_c, prefs2 = load_session(f); assert prefs2["theme"] == "custom" and prefs2["custom_theme"]["accent"] == "#22ccaa"
ok("theme choice is saved in the session")
win.make_settings_dialog = orig_make
win.prefs["theme"] = "dark"; win._apply_prefs()

# hover-help switch
win.prefs["help_on"] = False; win._apply_prefs()
class _Ev(QEvent):
    def __init__(self): super().__init__(QEvent.ToolTip)
assert win._tip_gate.eventFilter(P.hq, _Ev()) is True and not P.hq.toolTip()
win.prefs["help_on"] = True; win._apply_prefs()
assert win._tip_gate.eventFilter(P.hq, _Ev()) is False and P.hq.toolTip()
ok("hover help can be switched off in Settings and back on")

# ================================================================== About box: author credit + link
import re
from PySide6.QtWidgets import QLabel
from ck2_gui import AUTHOR_NAME, AUTHOR_URL
html = win.about_html()
plain = re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ")
assert "Vibecoded by Sceledrus using Claude Sonnet 5.5" in plain, plain
assert AUTHOR_URL == "https://www.youtube.com/channel/UCfbv9irTqrpZehCk8V4OvZQ"
assert html.count("<a ") == 1 and f'href="{AUTHOR_URL}"' in html and f">{AUTHOR_NAME}</a>" in html
assert re.search(rf'<a [^>]*>{AUTHOR_NAME}</a> using Claude Sonnet 5.5', html), "only the name is the link"
assert "not affiliated" in plain and "unofficial front-end for the CorridorKey 2.0 runtime by Corridor Digital" in plain
opened = []
import ck2_gui.main_window as _mw
_orig_open = _mw.QDesktopServices.openUrl
_mw.QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toString()) or True)
try:
    win.open_author_link("https://example.com/evil"); assert opened == [], "only the author's address may be opened"
    def _click_link():
        box = win._about_box
        lab = box.findChild(QLabel, "qt_msgbox_label")
        assert lab is not None and lab.textFormat() == Qt.RichText and "Sceledrus" in lab.text()
        shot_name = "18_about_" + theme.CURRENT
        box.grab().save(str(shots / (shot_name + ".png")))
        lab.linkActivated.emit(AUTHOR_URL)                    # same signal a real click on the name sends
        box.accept()
    for th in ("dark", "light"):
        win.prefs["theme"] = th; win._apply_prefs(); opened.clear()
        QTimer.singleShot(150, _click_link)
        win.about()
        assert opened == [AUTHOR_URL], (th, opened)
finally:
    _mw.QDesktopServices.openUrl = _orig_open
    win.prefs["theme"] = "dark"; win._apply_prefs()
ok("Help > About says 'Vibecoded by Sceledrus using Claude Sonnet 5.5'; clicking Sceledrus opens only the channel link")

# ================================================================== privacy: "copy for a bug report"
msg = win.copy_scrubbed(r"python: C:\Users\Jane Doe\CorridorKey\venv\Scripts\python.exe")
clip_text = app.clipboard().text()
assert "Jane" not in clip_text and "<user>" in clip_text and "Copied" in msg, (clip_text, msg)
assert "No user folder names" in win.copy_scrubbed("GUI 0.3.0   all fine")
ok("System check > COPY FOR A BUG REPORT puts text on the clipboard without the account name")

# ================================================================== extra video-encoding options
P.enc_sec.set_open(True)
i = P.enc_profile.findData("Small files"); P.enc_profile.setCurrentIndex(i); P.enc_profile.activated.emit(i)
assert (s.codec, s.crf, s.preset, s.pix_fmt) == ("libx264", 20, "fast", "yuv444p"), (s.codec, s.crf)
cmd = build_command("python", "infer.py", c0, "/o")
assert cmd[cmd.index("--crf") + 1] == "20" and cmd[cmd.index("--preset") + 1] == "fast" and cmd[cmd.index("--pix_fmt") + 1] == "yuv444p"
ok("quick encoding profile fills codec / CRF / preset / pixel format")
P.crf.setValue(21); assert P.enc_profile.currentData() is None; ok("editing a value flips the profile back to Custom")
P.rate_mode.setCurrentIndex(1); assert not P.crf.isEnabled() and P.bitrate.isEnabled()
P.bitrate.setText("50M"); assert s.bitrate == "50M"
cmd = build_command("python", "infer.py", c0, "/o")
assert cmd[cmd.index("--bitrate") + 1] == "50M" and "--crf" not in cmd; ok("fixed bitrate replaces CRF on the command line")
P.bitrate.setText("fifty"); assert s.bitrate == "" and "--bitrate" not in build_command("python", "infer.py", c0, "/o")
ok("an invalid bitrate is never passed to ffmpeg")
P.rate_mode.setCurrentIndex(0); P.bitrate.setText("")
P.threads.setValue(6); P.pix.setCurrentText("yuv420p10le"); P.codec.setCurrentText("libx265"); P.preset.setCurrentText("slow")
cmd = build_command("python", "infer.py", c0, "/o")
assert cmd[cmd.index("--ffmpeg_threads") + 1] == "6" and cmd[cmd.index("--ffmpeg_codec") + 1] == "libx265"
assert cmd[cmd.index("--pix_fmt") + 1] == "yuv420p10le"; ok("threads / codec / pixel format reach infer.py")
P.fmt.setCurrentIndex(1); assert not P.rate_mode.isEnabled() and not P.threads.isEnabled(); P.fmt.setCurrentIndex(0)
i = P.enc_profile.findData("Review (README default)"); P.enc_profile.setCurrentIndex(i); P.enc_profile.activated.emit(i)
P.threads.setValue(2); assert (s.codec, s.crf, s.preset, s.pix_fmt, s.bitrate, s.threads) == ("libx264", 12, "medium", "yuv444p10le", "", 2)
cmd = build_command("python", "infer.py", c0, "/o"); assert not any(f in cmd for f in ("--crf", "--bitrate", "--ffmpeg_threads", "--pix_fmt"))
ok("README-default profile is the default: no extra flags")
win.select_clip(c2.id); assert P.frame_fps.isEnabled() and P.kind == "sequence"
P.frame_fps.setValue(30.0); assert c2.settings.frame_fps == 30.0
cmd = build_command("python", "infer.py", c2, "/o"); assert cmd[cmd.index("--frame_dir_fps") + 1] == "30"
win.select_clip(c0.id); assert not P.frame_fps.isEnabled(); ok("frame-folder frame rate is editable for sequences only")
P.enc_sec.set_open(False)

# ================================================================== subject marker
P.hint_mode.setCurrentIndex(P.hint_mode.findData("marker"))
assert s.hint_mode == "marker" and P.hq.value() == 75, P.hq.value()
assert P.marker_box.isVisibleTo(P) and not P.path_row.isVisibleTo(P) and not P.no_carry.isEnabled()
ok("Subject Marker mode shows the marker tools, hides the file picker, and starts trust at 0.75")
assert validate(c0) and "left-click" in validate(c0)[0]; ok("running without a marker is refused with a clear reason")
P.mk_place.setChecked(True)
assert win.viewer.left_view.marker_mode and win.viewer.frame_idx == 0 and win.viewer.mode == "input"

def click(view, nx, ny, button=Qt.LeftButton):
    sc, tl, (iw, ih) = view._geometry()
    pos = QPointF(tl.x() + nx * iw * sc, tl.y() + ny * ih * sc).toPoint()
    QTest.mouseClick(view, button, Qt.NoModifier, pos)
    app.processEvents()

lv = win.viewer.left_view
click(lv, A_XY[0] / W, A_XY[1] / Hh)
assert s.markers == [[round(A_XY[0] / W, 4), round(A_XY[1] / Hh, 4), 1]] or len(s.markers) == 1, s.markers
assert wait(lambda: s.hint_path and os.path.exists(s.hint_path)), "hint was not generated"
m = subject.read_gray(s.hint_path)
assert m.shape == (Hh, W) and m[A_XY[1], A_XY[0]] > 0.9 and m[B_XY[1], B_XY[0]] < 0.1 and m[5, 5] < 0.1
assert s.marker_frame == 0 and not validate(c0), validate(c0)
ok("a real mouse click on subject A builds a hint that keeps A and drops B and the screen")
assert win.media.available("hint") and win.viewer.left_view._overlay is not None and len(lv.markers) == 1
shot("14_marker_keep_A")
cmd = build_command("python", "infer.py", c0, "/o")
assert cmd[cmd.index("--hint_first_frame") + 1] == s.hint_path and "--hint_video" not in cmd
ok("the marker hint is passed to infer.py as --hint_first_frame")
click(lv, B_XY[0] / W, B_XY[1] / Hh)
wait(lambda: subject.read_gray(s.hint_path)[B_XY[1], B_XY[0]] > 0.9)
m = subject.read_gray(s.hint_path); assert m[A_XY[1], A_XY[0]] > 0.9 and m[B_XY[1], B_XY[0]] > 0.9
ok("a second keep-click adds subject B")
click(lv, B_XY[0] / W, B_XY[1] / Hh, Qt.RightButton)
wait(lambda: subject.read_gray(s.hint_path)[B_XY[1], B_XY[0]] < 0.1)
m = subject.read_gray(s.hint_path); assert m[A_XY[1], A_XY[0]] > 0.9 and m[B_XY[1], B_XY[0]] < 0.1 and s.markers[-1][2] == -1
ok("a right-click removes it again")
shot("15_marker_remove_B")
win.scrub.go(5); assert lv._overlay is None and lv.markers == []                 # markers belong to frame 1 only
n_before = len(s.markers); click(lv, 0.3, 0.3)
assert win.viewer.frame_idx == 0 and len(s.markers) == n_before; ok("clicking on another frame jumps back to the first processed frame instead of adding a marker")
win.scrub.go(0); assert lv._overlay is not None
win.params.mk_undo.click(); wait(lambda: len(s.markers) == n_before - 1)
wait(lambda: subject.read_gray(s.hint_path)[B_XY[1], B_XY[0]] > 0.9); ok("UNDO removes the last marker and rebuilds the hint")
def cov(): return float((subject.read_gray(s.hint_path) > 0.5).mean())
cov0 = cov()
P.mk_grow.setValue(20)
assert wait(lambda: cov() > cov0 + 0.002, 5), "grow had no effect"
P.mk_grow.setValue(-20)
assert wait(lambda: cov() < cov0 - 0.002, 5), "shrink had no effect"
P.mk_grow.setValue(0)
assert wait(lambda: abs(cov() - cov0) < 0.002, 5)
ok("grow / shrink and softness feed the hint")

# partial range moves the first processed frame -> stale markers are flagged, not silently used
P.limit.setValue(10); P.start.setCurrentIndex(1)
errs = validate(c0); assert errs and "frame 1" in errs[0] and "frame 8" in errs[0], errs
assert not P._mk_ok and "frame 8" in P.mk_status.text(); ok("markers made for another start frame are flagged with how to fix it")
P.mk_goto.click(); assert win.viewer.frame_idx == 7
P.limit.setValue(0); P.start.setCurrentIndex(0); win.scrub.go(0)

# run: the hint is rebuilt from the clicks right before inference, the sound plays once
played.clear(); win._skip_overwrite_prompt = True
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"), (c0.status, c0.message)
assert wait(lambda: len(played) == 1), played
ok("marker clip ran end-to-end; the completion sound played exactly once")
# apply to all keeps the other clip's own hint settings and markers
win.params.applyAll.emit(); assert c1.settings.hint_mode == "none" and c1.settings.markers == [] and c1.settings.hint_path == ""
ok("Apply to All keeps each clip's own hint mode and markers")
P.mk_clear.click(); wait(lambda: s.hint_path == ""); assert s.markers == [] and validate(c0)
ok("CLEAR removes markers and the hint")
P.mk_place.setChecked(False); P.hint_mode.setCurrentIndex(P.hint_mode.findData("none"))
assert not lv.marker_mode and lv._overlay is None and P.hq.value() == 95
ok("leaving Subject Marker mode turns the tool off and restores default trust")

# ================================================================== sound
played.clear(); win.prefs.update(sound_on=False)
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"); wait(lambda: False, 0.4)
assert played == []; ok("sound off -> silent")
win.prefs.update(sound_on=True, sound_chime="bell", sound_volume=50)
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"); wait(lambda: len(played) >= 1, 2)
assert len(played) == 1 and "chime_bell_50" in os.path.basename(played[0]) and SND.pack_check(played[0])
ok("built-in chime + volume: a valid WAV is played")
own = work / "mine.wav"; SND.write_wav(str(own), SND.synth("pop"))
d = win.make_settings_dialog(); d.show()
assert d.set_custom_sound(str(own)) and d.use_custom.isChecked(); v = d.values(); assert v["sound_use_custom"] and v["sound_custom"] == str(own)
played.clear(); assert d.test_sound() and "custom_done" in os.path.basename(played[-1])
mp3 = work / "mine.mp3"
import shutil, subprocess
if shutil.which("ffmpeg"):                  # MP3 conversion needs ffmpeg; skip that part on machines without it
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=1", str(mp3)], check=True)
    assert d.set_custom_sound(str(mp3)); assert "Converted" in d.sound_msg.text()
d.tabs.setCurrentIndex(2); app.processEvents(); d.grab().save(str(shots / "16_dialog_sound.png")); d.tabs.setCurrentIndex(0); app.processEvents(); d.grab().save(str(shots / "16b_dialog_general.png")); d._clear_sound(); assert not d.values()["sound_use_custom"]
d.reject()
ok("own audio clip: WAV used as-is, MP3 converted once, TEST plays it, CLEAR goes back to the built-in sound")
win.prefs.update(sound_use_custom=True, sound_custom=str(own)); played.clear()
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE"); wait(lambda: len(played) >= 1, 2)
assert "custom_done" in os.path.basename(played[0]); ok("a finished run plays the user's own clip")
win.prefs.update(sound_custom=str(work / "gone.wav")); played.clear(); assert win.play_done_sound()
assert "chime_" in os.path.basename(played[0]) and "could not be found" in win.sound.last_message
ok("a missing custom file falls back to the built-in sound instead of failing")
win.prefs.update(sound_use_custom=False)
played.clear(); os.environ["FAKE_FAIL"] = "1"; win.run_clips([c0]); assert wait(lambda: c0.status == "ERROR"); wait(lambda: False, 0.4)
del os.environ["FAKE_FAIL"]; assert played == []; ok("a failed run stays quiet")
os.environ["FAKE_DELAY"] = "2"; win.run_clips([c0]); assert wait(lambda: c0.status == "RUNNING"); win.stop()
assert wait(lambda: c0.status == "CANCELLED"); del os.environ["FAKE_DELAY"]; wait(lambda: False, 0.5)
assert played == []; ok("pressing Stop stays quiet")
win.sound.backend = lambda p: (_ for _ in ()).throw(RuntimeError("no audio device"))
assert win.play_done_sound() is False and "Playback failed" in win.sound.last_message
win.sound.backend = lambda p: played.append(p) or True; ok("a broken audio device cannot crash the app")

# ================================================================== Nuke / After Effects hand-off
win.run_clips([c0]); assert wait(lambda: c0.status == "COMPLETE")
nk = Path(win.export_to("nuke", quiet=True)); jsx = Path(win.export_to("ae", quiet=True))
t = nk.read_text(); assert t.count("Read {") >= 3 and "CK_Premult" in t and f"{c0.name}_cutout.mov" in t and "Merge2" not in t
j = jsx.read_text(); assert "importFile" in j and "setTrackMatte" in j and f"{c0.name}_fg.mp4" in j
ok(f"Nuke .nk and After Effects .jsx written next to the results ({nk.name}, {jsx.name})")
win.select_clip(c2.id); assert win.export_to("ae", quiet=True) == ""; ok("exporting a clip with no results is refused politely")

shot("17_final"); print("ALL FEATURE TESTS PASSED  (screenshots:", shots, ")")
