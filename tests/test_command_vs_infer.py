"""Every command the GUI can build must be accepted by the REAL infer.py argument parser and map to
the expected InferenceConfig. torch and corridorkey are stubbed, so no GPU or weights are needed.
Run after updating infer.py to catch CLI drift:  python tests/test_command_vs_infer.py"""
"""Run the REAL infer.py argparse + config construction with torch/corridorkey stubbed,
and check that every command the GUI can build is accepted and maps to the expected config."""
import sys, types, itertools, importlib, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))

captured = {}
# ---- stub torch + corridorkey.* so infer.py imports and runs main() without a GPU
torch = types.ModuleType("torch"); torch.cuda = types.SimpleNamespace(is_available=lambda: True)
sys.modules["torch"] = torch
pkg = types.ModuleType("corridorkey"); pkg.__path__ = []
rt = types.ModuleType("corridorkey.runtime")
class _Cfg:
    def __init__(self, **kw): self.__dict__.update(kw)
rt.InferenceConfig = _Cfg; rt.WriterConfig = _Cfg
class _RP:
    @staticmethod
    def from_package(root, weights): return "paths"
rt.RuntimePaths = _RP
rt.load_model = lambda paths, device="cuda": "model"
def run_inference(model, inp, out, cfg, wcfg, *, initial_hint_path, hint_video_path):
    captured.update(inp=inp, out=out, cfg=cfg, wcfg=wcfg, h1=initial_hint_path, hv=hint_video_path)
rt.run_inference = run_inference
vio = types.ModuleType("corridorkey.video_io"); vio.require_ffmpeg = lambda b: None
sys.modules.update({"corridorkey": pkg, "corridorkey.runtime": rt, "corridorkey.video_io": vio})
infer = importlib.import_module("infer")

from ck2_gui.model import OUTPUT_KEYS, Clip, Settings, build_command
tmp = Path(tempfile.mkdtemp())
(tmp/"a.mp4").write_bytes(b"x"); (tmp/"hint.png").write_bytes(b"x"); (tmp/"hint.mp4").write_bytes(b"x")
(tmp/"frames").mkdir(); (tmp/"frames"/"f_0001.exr").write_bytes(b"x")

def run(clip, out="/o"):
    captured.clear()
    cmd = build_command("python", "infer.py", clip, out, ffmpeg_bin="")
    sys.argv = cmd[1:]
    infer.main()
    return cmd, captured["cfg"], captured["wcfg"]

n = 0
# 1. defaults, video
c = Clip(str(tmp/"a.mp4"), "video", "a"); cmd, cfg, w = run(c)
assert cfg.auto_vram is True and cfg.outputs == {"alpha","fg","checker","cutout"} and cfg.despill_strength == 0.5, cfg.__dict__
assert cfg.output_format == "video" and w.crf == 12; n += 1
# 2. first-frame hint
c.settings.hint_mode, c.settings.hint_path, c.settings.hint_quality = "first", str(tmp/"hint.png"), 0.75
cmd, cfg, w = run(c); assert captured["h1"] == str(tmp/"hint.png") and cfg.hint_quality == 0.75 and cfg.carry_hint is True; n += 1
# 3. full hint video, authoritative
c.settings.hint_mode, c.settings.hint_path, c.settings.no_carry = "video", str(tmp/"hint.mp4"), True
cmd, cfg, w = run(c); assert captured["hv"] == str(tmp/"hint.mp4") and cfg.carry_hint is False; n += 1
# 4. manual memory + low vram + partial clip
s = c.settings; s.no_carry = False; s.auto_vram = False; s.low_vram = True; s.hann_chunk, s.hann_stride = 8, 4
s.temp_dir = "/big/tmp"; s.num_frames = 100; s.start_mode = "random_middle"; s.seed = 7; s.stage2_batch = 2
cmd, cfg, w = run(c)
assert (cfg.hann_chunk, cfg.hann_stride, cfg.auto_vram, cfg.low_vram) == (8, 4, False, True)
assert (cfg.num_frames, cfg.start_mode, cfg.seed, cfg.stage2_batch) == (100, "random_middle", 7, 2) and str(cfg.temp_dir) == "/big/tmp"; n += 1
# 5. EXR output, float, cutout linear flag must be dropped for exr
s2 = Settings(output_format="exr", exr_dtype="float", cutout_linear=True, outputs=["fg","cutout"], despill=0.75)
c2 = Clip(str(tmp/"a.mp4"), "video", "a", settings=s2); cmd, cfg, w = run(c2)
assert cfg.output_format == "exr" and cfg.exr_dtype == "float" and cfg.outputs == {"fg","cutout"} and cfg.cutout_linear is False and cfg.despill_strength == 0.75; n += 1
# 6. frame sequence, linear, fps
s3 = Settings(frame_linear=True, frame_fps=25.0, num_frames=10, start_mode="middle")
c3 = Clip(str(tmp/"frames"), "sequence", "frames", settings=s3); cmd, cfg, w = run(c3)
assert cfg.frame_dir_linear is True and cfg.frame_dir_fps == 25.0 and cfg.num_frames == 10 and "--start_mode" not in cmd; n += 1
# 7. encoding overrides
s4 = Settings(codec="libx265", crf=18, preset="slow", pix_fmt="yuv444p", model_scale=0.5)
c4 = Clip(str(tmp/"a.mp4"), "video", "a", settings=s4); cmd, cfg, w = run(c4)
assert (w.codec, w.crf, w.preset, w.pix_fmt, cfg.model_scale) == ("libx265", 18, "slow", "yuv444p", 0.5); n += 1
# 7b. extra encoding controls: bitrate replaces CRF, threads, 4:2:0 pixel format
s5 = Settings(bitrate="50M", threads=6, pix_fmt="yuv420p10le", crf=20)
c5 = Clip(str(tmp/"a.mp4"), "video", "a", settings=s5); cmd, cfg, w = run(c5)
assert w.bitrate == "50M" and w.threads == 6 and w.pix_fmt == "yuv420p10le" and "--crf" not in cmd; n += 1
s5.bitrate = ""; cmd, cfg, w = run(c5); assert w.bitrate is None and w.crf == 20; n += 1
# 7c. subject marker: the generated PNG travels as the first-frame hint, with its own hint quality
s6 = Settings(hint_mode="marker", hint_path=str(tmp/"hint.png"), hint_quality=0.75, markers=[[0.4, 0.5, 1]], marker_frame=0)
c6 = Clip(str(tmp/"a.mp4"), "video", "a", frames=24, settings=s6); cmd, cfg, w = run(c6)
assert captured["h1"] == str(tmp/"hint.png") and captured["hv"] is None and cfg.hint_quality == 0.75 and "--hint_video" not in cmd; n += 1
# 8. exhaustive sweep of the boolean/enum space: nothing may make argparse reject the command
combos = 0
for hm, nc, av, lv, fmt, ob, br, pf in itertools.product(("none","marker","first","video"), (False,True), (True,False), (False,True), ("video","exr"),
                                                  (["alpha"], list(OUTPUT_KEYS), ["checker","cutout"]), ("", "8000k"), ("yuv444p10le", "yuv420p")):
    st = Settings(hint_mode=hm, hint_path=str(tmp/"hint.png") if hm!="none" else "", no_carry=nc, auto_vram=av, low_vram=lv, output_format=fmt, outputs=ob,
                  bitrate=br, pix_fmt=pf, threads=3)
    run(Clip(str(tmp/"a.mp4"), "video", "a", settings=st)); combos += 1
print(f"OK: {n} targeted checks, {combos} sweep combos accepted by the real infer.py parser")
print("sample:", " ".join(build_command("python","infer.py",c,"/o")))
