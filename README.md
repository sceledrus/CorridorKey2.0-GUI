# CorridorKey 2.0 — The Unofficial GUI

![version](https://img.shields.io/badge/version-0.3.0-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![license](https://img.shields.io/badge/licence-Corridor%20Key%20Licence%202.0-orange)
![privacy](https://img.shields.io/badge/telemetry-none-brightgreen)

**A point-and-click desktop front-end for [CorridorKey 2.0](https://corridorkey.com), the AI green-screen keyer from Corridor Digital.**
Drop in your clip, tune the settings with sliders and menus, press **Run**. No command line, no typing flags, no accounts.

> Vibecoded by [Sceledrus](https://www.youtube.com/channel/UCfbv9irTqrpZehCk8V4OvZQ) using Claude Sonnet 5.5.
> This is an unofficial community project. It is **not affiliated with or endorsed by Corridor Digital.**


## Contents

- [What this is](#what-this-is)
- [What you can do with it](#what-you-can-do-with-it)
- [Command line vs. this GUI](#command-line-vs-this-gui)
- [Install](#install)
- [Quick start](#quick-start)
- [Window layout](#window-layout)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Settings reference](#settings-reference)
- [Requirements](#requirements)
- [Privacy](#privacy)
- [Limitations](#Limitations)
- [Repository layout](#repository-layout)
- [Credits and licence](#credits-and-licence)

---

## What this is

CorridorKey 2.0 is run from the command line through `infer.py`. This project wraps that script in a normal desktop
window. Every time you press **Run**, the GUI builds the same command you would have typed and runs the official
`infer.py` as a separate process. The GUI never loads the AI model itself, so the keying results are exactly what the
command line would give you. The exact command of every job is printed at the top of its log, so you can always see
(and copy) what was run.

Think of it as a dashboard: the engine is untouched, you just get a cockpit.

## What you can do with it

### Key footage without touching a terminal
- **Import** a video file, a folder of frames (EXR, PNG, JPG), or a whole folder of clips by dropping them on the window.
- **Queue** as many clips as you like and run the selected one or all of them in one go. Stop at any time.
- **Per-clip settings**, plus an *Apply to all clips* button when you want one look across a batch.
- Companion hint files sitting next to a clip are detected automatically.

### Control every setting `infer.py` offers
- **Hint modes**: none, first-frame image, hint video, or the built-in Subject Marker (below).
- **Despill strength**, colour space, linear-light cutout, and model scale.
- **GPU memory**: automatic, or manual control (window and stride, low-VRAM mode, cache folder, stage-2 batch size).
- **Frame range**: process a short test section before committing to the full clip.
- **Outputs**: foreground, matte, composite and cutout, as video or as EXR sequences.
- **Video encoding**: quick profiles (default, high quality, small files, compatible 8-bit, H.265), codec, constant-quality or
  target-bitrate rate control, preset, pixel format, ffmpeg threads, and the frame rate for numbered-frame folders.

### Review your results properly
- **Dual viewer** with Input, Hint, FG, Matte, Comp and Proc tabs, an **A/B wipe**, and pan/zoom that stays linked between views.
- A **frame scrubber** that shows which frames will be processed and which already have output.
- A **live console** for each job, with the full command at the top.

### Subject Marker
Click the person or object you want to keep (left-click = keep, right-click = remove) and the GUI builds the first-frame hint
for you. Grow/shrink and softness sliders refine the edge before it is saved. It is a quick way to point the model at the
right subject without painting a matte by hand. See [Honest limits](#honest-limits) for what it can and cannot do.

### Help that explains itself
Hover any section, slider, button or viewer tab and a plain-language tooltip appears **right next to your mouse**, written for
people new to keying. While you drag a slider or change a dropdown, the tooltip also adds a *"Right now:"* sentence that explains
what your current value does. Prefer a quiet interface? Switch it off in Settings.

### Hand the result to your compositor
- **Nuke**: *File > Send Results to Nuke (.nk)* writes a script that creates Read nodes for the outputs you made, a Premult after the
  cutout, and a note on how to merge it over your background.
- **After Effects**: *File > Send Results to After Effects (.jsx)* writes a script that imports the outputs into a project folder and
  builds a correctly sized comp, with the matte set up as a track matte when there is no cutout.
- Both scripts only create nodes and layers. They never modify or delete your files.

### Make it yours
- **Dark**, **Light** and a **Custom theme maker**: pick six colours and every other shade is worked out for you, with import and export.
- A **"done" sound** when the queue finishes: four built-in chimes, or your own audio file. On or off.

## Command line vs. this GUI

| | Command line (`infer.py`) | This GUI |
|---|---|---|
| Starting a job | Type a command with flags | Press **Run** |
| Learning what a setting does | Read the docs | Hover it |
| Several clips | Script it yourself | Drop them in, **Run all** |
| Seeing the result | Open files elsewhere | Built-in viewer with A/B wipe and scrubber |
| Choosing a subject | Prepare a hint image yourself | Click it (Subject Marker) |
| Encoding choices | Remember the flags | Menus and profiles |
| Getting into Nuke / After Effects | Set up the shot by hand | One menu item writes the script |
| Result quality | Official engine | Identical (same engine, same flags) |

## Install

You need [**CorridorKey 2.0 working first**](https://github.com/nikopueringer/CorridorKey2.0) (NVIDIA GPU with CUDA-enabled PyTorch, the model weights, and `ffmpeg`). Follow
Corridor Digital's own instructions for that. This GUI is an add-on that lives inside the same folder.

### Windows (recommended)

1. Open the **[Releases](../../releases)** page and download `CorridorKey2-<version>-launcher.zip`.
   Optionally compare it with `SHA256SUMS.txt` from the same release.
2. Extract it **into your CorridorKey folder** (the one that contains `infer.py`).
3. Double-click **`CorridorKey2.exe`**.

If PySide6 (the window toolkit) is missing, the launcher asks first and then installs only that. Nothing else is installed and
nothing happens without your yes.

> **"Windows protected your PC"?** The exe is not code-signed (certificates cost money and this is a free hobby project).
> Click **More info > Run anyway**. If you would rather not, read the source in `launcher/launcher.c`, rebuild it yourself, or
> skip the exe and run `python run_gui.py` from your CorridorKey environment.

### Standalone window (optional)

`CorridorKey2-<version>-standalone-win64.zip` packs the window into a normal Windows program that opens without Python.
The AI model still runs in your existing CorridorKey environment (it needs several GB of PyTorch and weights that cannot fit in
an exe), so extract this one **inside your CorridorKey folder** as well. It is built automatically by GitHub Actions from this
repository. If it misbehaves, use the launcher zip instead.


## Quick start

1. **Import**: drop a clip, a frame folder, or a folder of clips onto the window.
2. **Pick a clip** in the tray at the bottom and adjust the panel on the right. Hover anything you are unsure about.
3. *(Optional)* Set **Hint** to *Subject Marker*, press **PLACE MARKERS**, and click the subject in the viewer.
4. Press **RUN INFERENCE** (`Ctrl+R`), or **RUN ALL** (`Ctrl+Shift+R`) for the whole queue.
5. **Review** with the viewer tabs and the A/B wipe.
6. *(Optional)* **File > Send Results to Nuke / After Effects**.

Tip: try a short frame range first. A few seconds of footage tells you whether the settings are right before you commit to the full clip.

## Window layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  CORRIDORKEY 2.0      GPU / VRAM meter                               │
├──────────┬───────────────────────────────────────────┬───────────────┤
│  Queue   │   Input viewer        │   Result viewer   │  Parameter    │
│  rail    │   (INPUT / HINT)      │   (FG / MATTE /   │  panel        │
│          │                       │    COMP / PROC)   │  (Hint, GPU,  │
│          │                       │                   │  Output, ...) │
├──────────┴───────────────────────────────────────────┴───────────────┤
│  Frame scrubber                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  Input clips tray                    │  Export tray                  │
├──────────────────────────────────────────────────────────────────────┤
│  Status bar                                                          │
└──────────────────────────────────────────────────────────────────────┘
```

- **Queue rail**: the jobs waiting, running and finished.
- **Viewers**: your source on the left, the result on the right, with linked pan and zoom.
- **Parameter panel**: collapsible sections, one per group of settings.
- **Scrubber**: yellow bracket = frames that will be processed; yellow line = frames that already have output.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+R` | Run the selected clip(s) |
| `Ctrl+Shift+R` | Run every ready clip |
| `Esc` | Stop |
| `F1` – `F6` | Switch viewer tab: Input, Hint, FG, Matte, Comp, Proc |
| `A` | A/B wipe |
| `F12` | Show the console / job log |
| Middle-click a slider | Reset it to its default |

## Settings reference

| Panel section | What it controls |
|---|---|
| Hint | None, first-frame image, hint video, or Subject Marker; hint quality and how it carries forward |
| Subject Marker | Your clicks, grow/shrink, edge softness |
| Inference | Colour space, despill, linear-light cutout, model scale |
| GPU Memory | Automatic or manual window/stride, low-VRAM mode, cache folder, stage-2 batch |
| Frame Range | How many frames, where to start, random seed |
| Output | FG / Matte / Comp / Cutout; video or EXR; EXR bit depth |
| Video Encoding | Profile, codec, quality or bitrate, preset, pixel format, threads, frame rate |

**Settings dialog**: General (paths, help on/off, settings folder), Appearance (themes), Sound (done chime).
The full panel-to-flag mapping is in the [user guide](docs/GUIDE.md).

## Requirements

| | |
|---|---|
| **CorridorKey 2.0** | Installed and working (weights, CUDA PyTorch, ffmpeg on PATH) |
| **To run the GUI** | Python 3.10 – 3.12 with PySide6-Essentials, OpenCV and NumPy (`requirements-gui.txt`) |
| **Operating system** | Windows 10/11 (launcher and standalone exe); Linux and macOS via `python run_gui.py` |
| **GPU** | Whatever CorridorKey 2.0 itself needs; the GUI adds no GPU load of its own |

*Help > System Check* inspects your setup and tells you what is missing.

## Privacy

- **No telemetry, no accounts, no analytics, no update checks.** The window makes no network connections.
- The only network use anywhere is the optional `pip install PySide6-Essentials` that the launcher offers, after you say yes.
- The only link in the program is the author's name in *Help > About*, and it opens your browser only if you click it.
- Settings, sessions and logs stay on your computer in `%APPDATA%\CorridorKey2-GUI\`.
- `crash.log` and **System Check > COPY FOR A BUG REPORT** remove your account name from folder paths so they are safer to paste into a
  public issue. File and clip names are not changed, so skim them first.
- Release files are built by GitHub's servers from the source in this repository, not on a personal PC.

See [SECURITY.md](SECURITY.md) for how to report a problem privately.

## Limitations

- Built and tested by one person with an AI assistant. The GUI was tested only on Windows and on headless Linux inside my assistant.
- **Treat the Nuke and After Effects support as a convenience.**
- **Subject Marker uses classic image segmentation (OpenCV GrabCut), which struggles with hair,
  motion blur and subjects that match the background colour. It only affects the first processed frame, because that is the only hint
  `infer.py` accepts and the model carries it forward. For exact control on every frame, supply your own hint**
- There is no live keying preview.
- Previews are 8-bit. EXR files are tone-mapped for viewing only.

## Repository layout

```
ck2_gui/                the GUI (window, themes, help text, hint maker, sound, exports)
run_gui.py              starts the GUI (also: --check, --selftest)
launcher/               source of the small Windows launcher exe
build_exe.py / .bat     builds the standalone window exe
tests/                  tests that run without a GPU
docs/                   user guide and screenshots
requirements-gui.txt    the GUI's three Python dependencies
.github/workflows/      the build-and-release automation
```

This repository is a fork of Corridor Digital's CorridorKey 2.0 repository. The runtime files (such as `infer.py`) come from the
official project; the GUI adds the files above on top.

## Credits and licence

- **CorridorKey 2.0** is made by **Corridor Digital**; the model was designed and trained by Zachary Harris with Niko and Corridor Digital.
  Get the official runtime, weights and plugin at [corridorkey.com](https://corridorkey.com).
- The window layout is inspired by the community Corridor Key 1 GUI. No code from it is used.
- Licensed under the **Corridor Key Licence 2.0** (CC BY-NC-SA 4.0 plus Corridor Digital's additional terms); the full text is in
  [LICENSE](LICENSE). In short: free to use, but not to be sold or offered as a paid service, anything built on it stays free under the
  same licence and keeps the CorridorKey name, and large organisations need the official plugin seat. Read the licence itself, not this summary.
- Third-party libraries (Qt for Python / PySide6, OpenCV, NumPy, PyInstaller): see [THIRD_PARTY_NOTICES_GUI.md](THIRD_PARTY_NOTICES_GUI.md).

**Found a bug?** [Open an issue](../../issues/new/choose) and please follow the privacy checklist in the template.
