"""Stand-in for infer.py: same CLI surface and the same progress lines the real runtime prints,
but 'keys' with a crude colour-difference matte. Lets the GUI be exercised without a GPU/weights."""
import argparse, os, sys, time
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2, numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--input"); ap.add_argument("--output_dir")
ap.add_argument("--outputs", nargs="*", default=["alpha","fg"])
ap.add_argument("--num_frames", type=int, default=-1); ap.add_argument("--start_mode", default="begin"); ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--despill_strength", type=float, default=0.5); ap.add_argument("--output_format", default="video")
ap.add_argument("--low_vram", action="store_true"); ap.add_argument("--hann_chunk", type=int); ap.add_argument("--delay", type=float, default=float(os.environ.get("FAKE_DELAY", "0.05")))
a, _ = ap.parse_known_args()
if os.environ.get("FAKE_FAIL"): print("Loading CorridorKey v2 runtime weights: /x"); print("torch.OutOfMemoryError: CUDA out of memory"); sys.exit(1)
name = os.path.splitext(os.path.basename(os.path.normpath(a.input)))[0]
cap = cv2.VideoCapture(a.input); n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
n = n_total if a.num_frames <= 0 else min(a.num_frames, n_total); start = 0; ms = max(n_total - n, 0)
if ms > 0 and a.num_frames > 0:
    if a.start_mode == "middle": start = ms // 2
    elif a.start_mode == "random_middle": start = int(np.random.default_rng(a.seed).integers(ms // 4, (3 * ms) // 4 + 1))
os.makedirs(a.output_dir, exist_ok=True)
print("Loading CorridorKey v2 runtime weights: weights/corridorkey_v2.safetensors", flush=True); time.sleep(0.3)
if a.low_vram:
    print(f"    RVM continuous prepass: T={n}, chunk=4", flush=True); print(f"    frozen VFM prepass: T={n}, grid=10x6, chunk=4", flush=True)
else:
    print(f"  Auto VRAM: 24.0 GB available at {W}x{H} -> window 16/8", flush=True)
chunk, stride = 16, 8; starts = list(range(0, max(n - chunk, 0) + 1, stride))
if starts[-1] + chunk < n: starts.append(n - chunk)
print(f"    Hann stage1: chunk={chunk}, stride={stride}, windows={len(starts)}, baton_grid=40x23", flush=True)
sfx = {"alpha":"alpha","fg":"fg","checker":"checker_comp_despill%03d" % int(a.despill_strength*100),"cutout":"cutout"}
writers = {k: cv2.VideoWriter(os.path.join(a.output_dir, f"{name}_{sfx[k]}" + (".mov" if k=="cutout" else ".mp4")), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W,H)) for k in a.outputs}
cap.set(cv2.CAP_PROP_POS_FRAMES, start); frames = []
for i in range(n):
    ok, f = cap.read(); frames.append(f)
yy, xx = np.mgrid[0:H, 0:W]; chk = (((yy//16)+(xx//16))%2*32+64).astype(np.uint8)[...,None].repeat(3,2)
for i, f in enumerate(frames):
    b,g,r = [f[...,c].astype(np.float32) for c in range(3)]
    alpha = np.clip(1.0 - (g - np.maximum(r,b)) / 90.0, 0, 1)[...,None]
    fg = f.astype(np.float32).copy(); fg[...,1] = np.minimum(fg[...,1], np.maximum(fg[...,0], fg[...,2]))
    outs = {"alpha": np.repeat(alpha*255,3,2), "fg": fg, "checker": fg*alpha + chk*(1-alpha), "cutout": fg*alpha + chk*(1-alpha)}
    for k in a.outputs: writers[k].write(np.clip(outs[k],0,255).astype(np.uint8))
for wi, s0 in enumerate(starts, 1):
    time.sleep(a.delay); print(f"      window {wi}/{len(starts)} [{s0}:{min(s0+chunk,n)}]", flush=True)
for w in writers.values(): w.release()
print(f"  wrote {len(writers)} output video(s) for {name} ({n} frames @ {W}x{H})", flush=True)
