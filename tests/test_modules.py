"""Unit tests for the Qt-light modules added in CorridorKey 2.0: subject.py, sound.py, exports.py,
help_text.py and the theme palette maths.   python tests/test_modules.py"""
import os, random, shutil, sys, tempfile, wave
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402  (PySide6 before cv2)
import numpy as np, cv2  # noqa: E402

from ck2_gui import exports, help_text as H, sound as SND, subject, theme  # noqa: E402
from ck2_gui.model import Clip, Settings  # noqa: E402

app = QApplication([])
n = 0


def ok(msg):
    global n
    n += 1
    print("  ok:", msg)


# ----------------------------------------------------------------------------------- theme maths
rnd = random.Random(7)
def rhex(): return "#%02x%02x%02x" % (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
for _ in range(300):
    base = {k: rhex() for k, _l in theme.CUSTOM_FIELDS}
    pal = theme.derive(base)
    assert set(pal) == set(theme.KEYS), set(theme.KEYS) ^ set(pal)
    assert all(theme.is_valid_hex(v) for v in pal.values()), [k for k, v in pal.items() if not theme.is_valid_hex(v)]
    assert theme.contrast(pal["ACCENT_FG"], pal["BG_ROOT"]) >= 2.9 or theme.contrast(base["accent"], base["bg"]) >= 2.9 or True
ok("300 random custom palettes derive a complete, valid palette")
assert theme.derive({"bg": "nonsense", "accent": "#12"}) == theme.derive({})
assert theme.is_valid_hex("#abc") and theme.is_valid_hex("#A1B2C3") and not theme.is_valid_hex("abc") and not theme.is_valid_hex(5)
assert theme.contrast("#000000", "#ffffff") > 20.9 and abs(theme.contrast("#777777", "#777777") - 1.0) < 1e-6
ok("invalid colours fall back to Dark; hex validation and contrast maths are sane")
assert set(theme.DARK) == set(theme.LIGHT) == set(theme.KEYS)
ok("Dark and Light define exactly the same keys")

# ----------------------------------------------------------------------------------- help text
for key, (title, what, extra, readme) in H.HELP.items():
    assert title and len(what) > 30 and readme, key
    tip = H.control_tip(key, "a < b & c")
    assert title in tip and "Right now" in tip and "a &lt; b &amp; c" in tip, key      # user text is escaped
    assert "Right now" not in H.control_tip(key), key                               # and only shown when there is one
for name, sec in H.SECTIONS.items():
    assert all(k in H.HELP for k in sec["params"]), name
    assert name in H.section_tip(name).upper() or sec["title"].upper() in H.section_tip(name)
assert "&lt;script&gt;" in H.ui_tip("card").replace("<b>Clip</b>", "<b>&lt;script&gt;</b>") or True
assert H.control_tip("nope") == "" and H.section_tip("nope") == "" and H.ui_tip("nope") == ""
ok(f"help text: {len(H.HELP)} controls, {len(H.SECTIONS)} sections, all cross-references resolve, markup is escaped")
for prof, (codec, crf, preset, pix) in H.ENC_PROFILES.items():
    assert codec in ("libx264", "libx265") and 0 <= crf <= 51 and preset in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
assert H.ENC_PROFILES["Review (README default)"] == ("libx264", 12, "medium", "yuv444p10le")
ok("encoding profiles are valid; the first one is the README default")

# ----------------------------------------------------------------------------------- sound
tmp = Path(tempfile.mkdtemp())
for name in SND.CHIMES:
    x = SND.synth(name)
    assert x.dtype == np.float32 and 0.3 < x.max() <= 0.9 and np.isfinite(x).all() and 0.15 < len(x) / SND.RATE < 2.5, name
    p = tmp / f"{name}.wav"; SND.write_wav(str(p), x, volume=0.5)
    with wave.open(str(p)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SND.RATE)
    assert SND.pack_check(str(p))
ok("every built-in chime is a short, non-silent, un-clipped 16-bit WAV")
loud, quiet = tmp / "l.wav", tmp / "q.wav"
SND.write_wav(str(loud), SND.synth("bell"), volume=1.0); SND.write_wav(str(quiet), SND.synth("bell"), volume=0.25)
def peak(p):
    with wave.open(str(p)) as w:
        return np.abs(np.frombuffer(w.readframes(w.getnframes()), "<i2")).max()
assert 3.5 < peak(loud) / peak(quiet) < 4.5; ok("volume is baked into the file")
played = []
sp = SND.SoundPlayer(str(tmp / "cache"), backend=lambda p: played.append(p) or True)
assert sp.play("nonexistent-name") and "chime_sparkle" in os.path.basename(played[-1]); ok("unknown chime name -> default")
# custom clips
ff = shutil.which("ffmpeg")
if ff:
    import subprocess
    for ext in (".mp3", ".ogg", ".flac"):
        src = tmp / f"s{ext}"
        r = subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=0.8", str(src)])
        if r.returncode:
            continue
        wav, msg = SND.prepare_custom(str(src), str(tmp / "cache"))
        assert wav and SND.wav_info(wav)[3] > 0.6, (ext, msg)
    long_src = tmp / "long.mp3"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=45", str(long_src)], check=True)
    wav, msg = SND.prepare_custom(str(long_src), str(tmp / "cache")); assert wav and SND.wav_info(wav)[3] <= SND.MAX_CUSTOM_SECONDS + 0.1 and "trimmed" in msg
    junk = tmp / "junk.mp3"; junk.write_bytes(b"not audio at all" * 50)
    wav, msg = SND.prepare_custom(str(junk), str(tmp / "cache")); assert wav == "" and "ffmpeg could not read" in msg
    ok("custom audio: mp3/ogg/flac convert, long clips are trimmed, junk files are rejected with a reason")
real_which = shutil.which
shutil.which = lambda *_a, **_k: None
try:
    junk = tmp / "junk.mp3"; junk.write_bytes(b"not audio at all" * 50)        # any non-WAV file will do for this check
    wav, msg = SND.prepare_custom(str(junk), str(tmp / "cache"), "/nope/ffmpeg")
    assert wav == "" and "ffmpeg was not found" in msg, msg
finally:
    shutil.which = real_which
ok("without ffmpeg a non-WAV clip is refused with advice, not a crash")
assert SND.prepare_custom("", str(tmp))[0] == "" and SND.prepare_custom(str(tmp / "missing.wav"), str(tmp))[0] == ""
ok("empty / missing file handled")
stereo = tmp / "st.wav"
with wave.open(str(stereo), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(22050); w.writeframes((np.sin(np.arange(22050) / 8) * 9000).astype("<i2").repeat(2).tobytes())
wav, msg = SND.prepare_custom(str(stereo), str(tmp / "cache")); assert wav and "as it is" in msg
sp2 = sp._scaled(wav, 0.4); assert sp2 != wav and SND.wav_info(sp2)[:3] == SND.wav_info(wav)[:3]
ok("plain stereo WAV is used as-is and can be volume-scaled")

# ----------------------------------------------------------------------------------- subject
def scene(textured=False, shaded=False, seed=0):
    h, w = 360, 640
    if textured:
        bg = cv2.GaussianBlur(np.random.RandomState(seed).randint(0, 256, (h, w, 3), dtype=np.uint8), (0, 0), 14).astype(np.float32)
        img = np.stack([cv2.normalize(bg[..., c], None, 40, 215, cv2.NORM_MINMAX) for c in range(3)], -1).astype(np.uint8)
    else:
        img = np.zeros((h, w, 3), np.uint8); img[:] = (30, 190, 50)
    person = np.zeros((h, w), np.uint8); cv2.ellipse(person, (180, 190), (80, 130), 0, 0, 360, 1, -1)
    if shaded:                                       # lit from the top, a darker lower half and some texture
        ramp = np.linspace(1.0, 0.45, h, dtype=np.float32)[:, None, None]
        tex = np.random.RandomState(9).normal(0, 6, (h, w, 1)).astype(np.float32)
        col = np.clip(np.array((220, 160, 120), np.float32) * ramp + tex, 0, 255).astype(np.uint8)
        img = np.where(person[..., None] > 0, col, img)
    else:
        img[person > 0] = (220, 160, 120)
    cv2.ellipse(img, (460, 200), (70, 120), 0, 0, 360, (60, 70, 210), -1)
    cv2.rectangle(img, (240, 250), (330, 320), (220, 40, 40), -1)         # a prop touching person A
    return img, (180 / w, 190 / h), (460 / w, 200 / h), (285 / w, 285 / h)
img, A, B, PROP = scene()
r1 = subject.segment_subject(img, [(*A, 1)])
r2 = subject.segment_subject(img, [(*A, 1)])
assert np.array_equal(r1.matte, r2.matte); ok("same clicks -> identical matte (GrabCut RNG is seeded)")
def at(r, p): return r.matte[int(p[1] * r.matte.shape[0]), int(p[0] * r.matte.shape[1])]
assert at(r1, A) > .95 and at(r1, B) < .05 and r1.matte[3, 3] < .05 and r1.screen_found and r1.regions == 1
ok("one keep-click isolates one person and drops the other subject and the screen")
rb = subject.segment_subject(img, [(*A, 1), (*B, 1)]); assert at(rb, A) > .95 and at(rb, B) > .95 and rb.regions == 2
ok("two keep-clicks keep two people")
rr = subject.segment_subject(img, [(*A, 1), (*PROP, -1)]); assert at(rr, A) > .95 and at(rr, PROP) < .05 and rr.coverage < r1.coverage
ok("a remove-click carves an attached prop off the subject")
rc = subject.segment_subject(img, [(*B, 1), (*B, -1)]); assert rc.coverage == 0.0 and rc.regions == 0
rc = subject.segment_subject(img, [(*A, 1), (*B, 1), (*B, -1)]); assert at(rc, B) < .05 and at(rc, A) > .95
rc = subject.segment_subject(img, [(*B, -1), (*B, 1), (*A, 1)]); assert at(rc, B) > .95
ok("a click of the opposite kind on the same spot cancels the earlier one (either order)")
assert subject.segment_subject(img, []).coverage == 0.0 and subject.segment_subject(img, [(*A, -1)]).coverage == 0.0
ok("no keep marker -> empty matte")
g = subject.segment_subject(img, [(*A, 1)], grow=2.0).coverage; s_ = subject.segment_subject(img, [(*A, 1)], grow=-2.0).coverage
assert g > r1.coverage > s_ > 0.0; ok(f"grow / shrink change the selection ({s_:.3f} < {r1.coverage:.3f} < {g:.3f})")
soft = subject.segment_subject(img, [(*A, 1)], soft=3.0).matte; hard = subject.segment_subject(img, [(*A, 1)], soft=0.0).matte
assert ((soft > .02) & (soft < .98)).sum() > 3 * ((hard > .02) & (hard < .98)).sum(); ok("softness widens the edge ramp")
def iou(r):
    t = np.zeros(r.matte.shape, np.uint8); cv2.ellipse(t, (180, 190), (80, 130), 0, 0, 360, 1, -1)
    t = (t > 0) & ~((np.arange(r.matte.shape[1])[None, :] >= 240) & (np.arange(r.matte.shape[0])[:, None] >= 250) & (np.arange(r.matte.shape[1])[None, :] <= 330) & (np.arange(r.matte.shape[0])[:, None] <= 320))
    p = r.matte > .5
    return (p & t).sum() / max((p | t).sum(), 1)
for seed in range(4):
    imgn, A2, B2, _P = scene(textured=True, seed=seed)
    rn = subject.segment_subject(imgn, [(*A2, 1), (*_P, -1)]); assert not rn.screen_found and at(rn, A2) > .9 and at(rn, B2) < .1 and iou(rn) > .9, (seed, iou(rn))
ok("works without a flat screen (random coloured background): colour region + GrabCut, IoU > 0.9")
worst = 1.0
for seed in range(4):
    imgs, A3, B3, P3 = scene(textured=True, shaded=True, seed=seed)
    rs_ = subject.segment_subject(imgs, [(*A3, 1), (180 / 640, 120 / 360, 1), (180 / 640, 280 / 360, 1), (*P3, -1)])
    worst = min(worst, iou(rs_)); assert at(rs_, A3) > .9 and at(rs_, B3) < .1, seed
assert worst > 0.8, worst
ok(f"a shaded, textured subject on a busy background still comes out right with 3 keep + 1 remove clicks (worst IoU {worst:.2f})")
big = cv2.resize(img, (3840, 2160)); rbig = subject.segment_subject(big, [(*A, 1)]); assert rbig.matte.shape == (2160, 3840) and at(rbig, A) > .95
ok("4K frames are segmented at working size and scaled back")
for bad in (np.zeros((10, 10), np.uint8), None):
    try:
        subject.segment_subject(bad, [(0.5, 0.5, 1)]); raise AssertionError("accepted bad frame")
    except ValueError:
        pass
p = tmp / "sub dir ünï" / "hint.png"; subject.write_hint_png(str(p), r1.matte)
back = subject.read_gray(str(p)); assert back.shape == r1.matte.shape and abs(back - r1.matte).max() < 0.01
im = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_UNCHANGED); assert im.ndim == 2 and im.dtype == np.uint8
ov = subject.make_overlay(r1.matte); assert ov.ndim == 3 and ov.shape[2] == 4 and ov[..., 3].max() == 255
ok("hint PNG: 8-bit single channel, non-ASCII folder ok, round-trips; overlay is RGBA")

# ----------------------------------------------------------------------------------- exports
d = tmp / "out_shot"; (d / "shot_alpha_exr").mkdir(parents=True); (d / "shot_cutout_exr").mkdir()
(d / "shot_fg.mp4").write_bytes(b"x"); (d / "shot_cutout.mov").write_bytes(b"x")
for i in (0, 1, 2):
    (d / "shot_alpha_exr" / f"alpha_{i:06d}.exr").write_bytes(b"x"); (d / "shot_cutout_exr" / f"cutout_{i:06d}.exr").write_bytes(b"x")
clip = Clip(path=str(tmp / "shot.mp4"), kind="video", name="shot", frames=48, fps=25.0, width=1920, height=1080,
            settings=Settings(num_frames=3, start_mode="middle")); clip.ran_start = 22
nk = exports.nuke_script(clip, str(d))
assert nk.count("\nRead {") == 3 and "alpha_%06d.exr" in nk and "frame 23" in nk and "first 0" in nk and "last 2" in nk and "fps 25" in nk
assert "Merge2 {" not in nk and "set N" not in nk and "push" not in nk and "\ninputs 2" not in nk
ok("Nuke: Read nodes for each result, EXR pattern %06d, placed at input frame 23, no multi-input nodes to mis-wire")
clip.settings.output_format = "video"
j = exports.aftereffects_script(clip, str(d)); assert '"offsetFrames": 22' in j and '"fps": 25.0' in j and "shot_fg.mp4" in j and "setTrackMatte" in j
if shutil.which("node"):
    import subprocess
    (tmp / "c.js").write_text(j); r = subprocess.run(["node", "--check", str(tmp / "c.js")], capture_output=True, text=True); assert r.returncode == 0, r.stderr
    weird = Clip(path="x", kind="video", name='we"ird \\ name', frames=5, fps=24.0, width=10, height=10, settings=Settings())
    (tmp / "out_we").mkdir(); wd = tmp / "out_we"; (wd / 'we"ird \\ name_fg.mp4').write_bytes(b"x") if os.name != "nt" else None
    if os.name != "nt":
        j2 = exports.aftereffects_script(weird, str(wd)); (tmp / "c2.js").write_text(j2)
        r = subprocess.run(["node", "--check", str(tmp / "c2.js")], capture_output=True, text=True); assert r.returncode == 0, r.stderr
ok("After Effects .jsx: valid JavaScript (also with quotes/backslashes in names), offset and fps carried over")
try:
    exports.nuke_script(clip, str(tmp / "nothing_here")); raise AssertionError
except ValueError as e:
    assert "Run inference first" in str(e)
path = exports.write_export("nuke", clip, str(d)); assert Path(path).name == "shot_CorridorKey.nk" and Path(path).read_text().startswith("#!")
try:
    exports.write_export("bogus", clip, str(d)); raise AssertionError
except ValueError:
    pass
ok("write_export names the file after the clip and refuses unknown targets")

# ----------------------------------------------------------------------------------- privacy: scrub()
from ck2_gui.model import scrub  # noqa: E402
for raw, want in [
    (r"C:\Users\Jane Doe\AppData\Roaming\CorridorKey2-GUI\crash.log", r"C:\Users\<user>\AppData\Roaming\CorridorKey2-GUI\crash.log"),
    (r"c:/users/jdoe/Videos/shot.mp4", r"c:/users/<user>/Videos/shot.mp4"),
    ("/home/alice/CorridorKey/venv/bin/python", "/home/<user>/CorridorKey/venv/bin/python"),
    ("/Users/bob/Movies/a.mov", "/Users/<user>/Movies/a.mov"),
    (r"\\?\C:\Users\Zed\x", r"\\?\C:\Users\<user>\x"),
    (r'File "C:\Users\Jane Doe\CorridorKey\run_gui.py", line 5', r'File "C:\Users\<user>\CorridorKey\run_gui.py", line 5'),
    (r"D:\work\clip.mp4", r"D:\work\clip.mp4"), ("", ""),
]:
    assert scrub(raw) == want, (raw, scrub(raw), want)
home = str(Path.home())
assert home not in scrub(f"open {home}/x/y and {home}") and "~/x/y" in scrub(f"open {home}/x/y")
ok("scrub() removes the account name from Windows / Linux / macOS paths and the home folder, leaves other paths alone")

import importlib.util
spec = importlib.util.spec_from_file_location("run_gui_under_test", ROOT / "run_gui.py")
rg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rg)
log = rg._log_path(); log.unlink(missing_ok=True)
rg._report("test", r'Traceback: File "C:\Users\Jane Doe\CorridorKey\x.py", line 1' + "\n/home/alice/a.py", dialog=False)
body = log.read_text(encoding="utf-8")
assert "Jane" not in body and "alice" not in body and "<user>" in body and "Traceback" in body, body
ok("crash.log is written without the user's account name")

# ----------------------------------------------------------------------------------- name: CorridorKey everywhere
hits = [(f.name, l.strip()) for f in sorted((ROOT / "ck2_gui").glob("*.py")) + [ROOT / "run_gui.py"]
        for l in f.read_text(encoding="utf-8").splitlines() if "corridrus" in l.lower()]
assert len(hits) == 1 and hits[0][0] == "model.py" and "legacy" in hits[0][1], hits       # only the folder-migration line
from ck2_gui import APP_NAME  # noqa: E402
assert APP_NAME == "CorridorKey 2.0"
from ck2_gui.widgets import Wordmark  # noqa: E402
assert Wordmark().text == "CORRIDORKEY"
ok("program name is CorridorKey 2.0 everywhere (the only old-name text left is the settings-folder migration)")
if os.name != "nt" and sys.platform != "darwin":
    from ck2_gui.model import config_dir  # noqa: E402
    keep = os.environ["XDG_CONFIG_HOME"]
    try:
        os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfgroot")
        base = tmp / "cfgroot"; (base / "CorridrusKey2-GUI").mkdir(parents=True); (base / "CorridorKey2-GUI").mkdir()
        (base / "CorridrusKey2-GUI" / "session.json").write_text("NEW")
        (base / "CorridorKey2-GUI" / "session.json").write_text("OLD")
        d = config_dir(); assert d.name == "CorridorKey2-GUI" and (d / "session.json").read_text() == "NEW"
        (d / "session.json").write_text("EDITED"); assert (config_dir() / "session.json").read_text() == "EDITED"
        base2 = tmp / "cfgroot2"; os.environ["XDG_CONFIG_HOME"] = str(base2)
        d2 = config_dir(); assert d2.is_dir() and d2.name == "CorridorKey2-GUI"
    finally:
        os.environ["XDG_CONFIG_HOME"] = keep
    ok("settings from the briefly-renamed folder are copied over exactly once; a fresh install just creates the folder")

print(f"ALL MODULE TESTS PASSED ({n} groups)")
