# CorridorKey 2.0 (unofficial GUI)

**An unofficial desktop GUI for [CorridorKey 2.0](https://corridorkey.com)**, the AI green-screen keyer from Corridor Digital.
Drop in a clip, adjust the settings, press Run. Free, private, and it never touches the model itself.

> Vibecoded by [Sceledrus](https://www.youtube.com/channel/UCfbv9irTqrpZehCk8V4OvZQ) using Claude Sonnet 5.5.
> An unofficial front-end for the CorridorKey 2.0 runtime by Corridor Digital. **Not affiliated with or endorsed by Corridor Digital.**

![CorridorKey 2.0 in Subject Marker mode](docs/screenshots/main-dark.png)

## What it does

- **Everything `infer.py` can do, with buttons**: hint modes, despill, model scale, GPU-memory presets, frame range,
  outputs (FG / Matte / Comp / Cutout), video or EXR, queue, batch run, A/B wipe, linked zoom. Every job's exact command
  is shown in the console, and the GUI runs the official `infer.py` as a separate process, so results match the command line.
- **Hover help for every setting**, written for people new to keying, with a "Right now:" line that explains your current value.
- **Subject Marker**: click the person or object you want to keep (right-click to exclude) and it builds the first-frame hint for you.
- **Video encoding options**: quick profiles, CRF or target bitrate, codec, preset, pixel format, threads, frame rate.
- **Dark, Light and a Custom theme maker** (six colours, import/export).
- **A "done" sound** (four built-in chimes, or your own audio file), on or off.
- **Send results to Nuke (.nk) or After Effects (.jsx)**: writes a small script that imports your outputs.

More detail: [docs/GUIDE.md](docs/GUIDE.md).

## Install (Windows)

You need CorridorKey 2.0 working first (NVIDIA GPU with CUDA PyTorch, the weights, and `ffmpeg`): follow its own README.
This GUI is an add-on that sits inside that folder.

1. Go to **[Releases](../../releases)** and download `CorridorKey2-<version>-launcher.zip` (and check it against `SHA256SUMS.txt`).
2. Extract it **into your CorridorKey folder**, the one that contains `infer.py`.
3. Double-click **`CorridorKey2.exe`**. If PySide6 is missing it offers to install it (your yes first); nothing else is installed.

Windows may say "Windows protected your PC" because the exe is not code-signed (a certificate costs money and
this is a free hobby project). Click **More info**, then **Run anyway**. Don't trust the file? You can read all of its
source in `launcher/launcher.c`, rebuild it yourself, or skip it and run `python run_gui.py` from your CorridorKey venv.

**Standalone version** (`CorridorKey2-<version>-standalone-win64.zip`): the window itself is frozen into a normal Windows
program that doesn't need Python to open. The AI model still runs in your CorridorKey Python environment (a multi-GB model
can't be packed into an exe), so extract that zip **inside** your CorridorKey folder too. It is built automatically by GitHub
Actions from this repository; if it gives you any trouble, use the launcher zip.

**Linux / macOS**: `pip install -r requirements-gui.txt` into the CorridorKey venv, then `python run_gui.py`.

## Privacy

- **No telemetry, accounts, analytics or update checks.** The window itself makes no network connections.
- The only network use anywhere is the *optional* `pip install PySide6-Essentials` the launcher offers, after you say yes.
- The only link in the program is the author's name in Help > About; it opens your browser only if you click it.
- Settings, sessions and logs live in `%APPDATA%\CorridorKey2-GUI\` (Linux: `~/.config/CorridorKey2-GUI/`). Nothing leaves your machine.
- `crash.log` and **System check > COPY FOR A BUG REPORT** remove your account name from folder paths, so
  they are safe to paste into a public issue. Still skim them; file and clip names are not touched.
- The released files are built on GitHub's servers from the source in this repository, so the build machine is not anyone's PC.

## Honest limits

- Built and tested by one person, with an AI. The GUI, the launcher and the tests run on the author's Windows PC and on
  headless Linux. **The Nuke and After Effects scripts have not been run inside Nuke or After Effects**; they follow the documented
  formats and only create nodes/layers, so treat them as a convenience that may need a small fix.
- The Subject Marker is a **rough hint, not a hard cut**: it is built with classic image segmentation (OpenCV GrabCut), which
  struggles with hair, motion blur and subjects the same colour as the background. It only affects the first processed frame, which
  is all `infer.py` accepts as a hint; the model carries it forward.
- The completion sound, hover help and themes were tested headless; the sound itself has not been checked on every sound card.

## Credits and license

- **CorridorKey 2.0** is by Corridor Digital. The model was designed and trained by Zachary Harris with Niko and Corridor Digital.
  Get it, the weights and the official plugin at [corridorkey.com](https://corridorkey.com). The layout is inspired by the community Corridor Key 1 GUI;
  no code from it is used.
- This project is licensed under the **Corridor Key Licence 2.0** (CC BY-NC-SA 4.0 plus Corridor Digital's additional terms), copied
  verbatim in [LICENSE](LICENSE). In short: free to use, including commercially, but it may not be sold or offered as a paid service,
  anything built on it must stay free under the same licence and keep the CorridorKey name, and organisations above US$20M
  annual revenue need the official plugin seat. Read the licence, not this paragraph.
- Third-party libraries (Qt for Python / PySide6, OpenCV, NumPy, PyInstaller): see [THIRD_PARTY_NOTICES_GUI.md](THIRD_PARTY_NOTICES_GUI.md).
- This repository does **not** contain CorridorKey's code or weights. You get those from Corridor Digital.

Found a bug? [Open an issue](../../issues/new/choose) and please use the privacy checklist in the template.
