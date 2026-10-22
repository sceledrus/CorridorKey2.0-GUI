# CorridorKey 2.0 - user guide

A desktop front-end for CorridorKey 2.0's `infer.py`, laid out like the Corridor Key 1 GUI (brand bar with GPU/VRAM
meter, queue rail, dual input/result viewer, parameter panel, scrubber, input/export tray, status bar).

It does **not** load the model itself. Each run is `python infer.py ...` in a subprocess, built the same way
`run_interactive.py` builds it, so results are identical to the command line.

> Vibecoded by Sceledrus using Claude Sonnet 5.5. An unofficial front-end for the CorridorKey 2.0 runtime by Corridor Digital;
> not affiliated with or endorsed by Corridor Digital.

## What is a "native exe" here, and what is not

The window (everything you click) can be a normal Windows program. The AI model cannot: it needs PyTorch, CUDA and several
GB of weights, which no small exe can carry. So both downloads keep using the Python environment you already made for
CorridorKey to run the model:

| Download | What it is | Needs Python to open the window? |
|---|---|---|
| `...-launcher.zip` | Small launcher exe (~84 KB) plus the GUI's Python files. The exe finds your `venv`, checks it, and opens `run_gui.py` inside it. | Yes (your CorridorKey venv) |
| `...-standalone-win64.zip` | The window itself frozen with PyInstaller together with PySide6, OpenCV and numpy. | **No** for the window. Each run still starts `infer.py` with the venv's Python. |

PyInstaller cannot cross-compile, so the standalone exe is built on a Windows machine (GitHub's, via the workflow in
`.github/workflows/release.yml`). If it misbehaves, the launcher version is the well-tested one.

## Install and launch

**Launcher (recommended).** Extract the zip into the CorridorKey 2.0 folder, the one that contains `infer.py`, then
double-click `CorridorKey2.exe`. You can also drop clips or frame folders onto the exe.

- Before opening the window it checks that this Python can import PySide6 and OpenCV/numpy (it runs
  `python -c "import ..."` itself). If PySide6 is simply not installed it asks before running
  `pip install PySide6-Essentials` (about 80 MB, in a visible console window). It installs nothing else, and nothing
  without your yes. It looks for `venv\`, `.venv\` or `env\` next to the exe first, otherwise `python` on PATH.
- Windows may show "Windows protected your PC" because the exe is not code-signed. Click **More info**, then
  **Run anyway**. To check your download, compare `certutil -hashfile CorridorKey2-<version>-launcher.zip SHA256`
  with `SHA256SUMS.txt` on the release page.
- If anything fails, the exe shows a message that includes Python's own error text (captured to
  `%TEMP%\corridorkey2_launcher.log`). Errors inside the GUI are appended to `%APPDATA%\CorridorKey2-GUI\crash.log`
  with your account name removed from any path.
- Rebuild the launcher yourself (no Windows needed, no Visual Studio): `pip install ziglang pillow`, then
  `python launcher/build.py`. The source is ~300 lines in `launcher/launcher.c`.

**Standalone window.** Extract the zip inside your CorridorKey folder (it can sit up to three folders below `infer.py`).
At start-up it walks upward to find `infer.py`, then uses `venv\`, `.venv\` or `env\` there, otherwise `python` on PATH. If you
put it somewhere else, set the paths in Settings > General.

Build it yourself on Windows (Python 3.10-3.12 and internet access):

```
build_exe.bat                  # -> dist\CorridorKey2\CorridorKey2.exe   (folder build, starts fastest)
build_exe.bat --onefile        # -> dist\CorridorKey2.exe                  (one file, slower first start)
build_exe.bat --selftest       # after building, start it once off-screen and check it is healthy
```

It makes a throw-away build environment in `build_gui\` and installs PySide6, OpenCV, numpy and PyInstaller there (never into your
CorridorKey venv). Only the Qt parts the window uses are included.

**Without any exe**

```
pip install -r requirements-gui.txt        # into the same venv you use for CorridorKey (PySide6, OpenCV, numpy)
python run_gui.py                          # or CorridorKey_GUI.bat / CorridorKey_GUI.sh
python run_gui.py shot.mp4 plates_folder   # import on launch
python run_gui.py --selftest               # build the window off-screen and check it; exit code 0 means healthy
```

Setup from the CorridorKey README still applies (weights via `scripts/download_weights.py`, ffmpeg on PATH).
Help > System Check shows what is missing.

## Workflow

1. Drop a clip, a frame folder (EXR/PNG/JPG), or a folder of clips onto the window.
   Companion files are detected like the launcher does: `<clip>_AlphaHint.mp4` (full hint video),
   `<clip>FrameHint.png` (first-frame hint), and an `AlphaHint/` folder next to an `Input/` frame folder.
2. Pick the clip in the tray and adjust the right-hand panel. Settings are per clip; middle-click a slider
   to reset it; "Apply to all clips" copies the settings (not hints/colour space/output folders; Subject Marker
   clicks are kept per clip).
3. RUN INFERENCE (Ctrl+R) for the selection, RUN ALL (Ctrl+Shift+R) for every ready clip, Esc to stop.
4. Review with INPUT / HINT / FG / MATTE / COMP / PROC (F1-F6), A for an A/B wipe. Pan and zoom are linked.
5. Optional: File > Send Results to Nuke (.nk) / After Effects (.jsx).

## Features

### Hover help for everything

Hover a section header, a parameter, a button or a viewer tab and a tooltip appears next to the mouse and explains it in plain
language, written from the CorridorKey README. For settings with a value (like Hint Quality) the tooltip ends with a
"Right now: ..." sentence describing what your current value means. Don't want it? Untick Settings > General > Help >
**Show hover explanations** (tick it again any time).

### Themes (Settings > Appearance)

* **Dark (Corridor)** is the default. **Light (White)** is a white theme. **Custom** is the theme maker.
* The theme maker takes six colours (background, panel, text, accent, OK, danger) and works out every other shade
  from them (an accent colour that would be hard to read on your background is lightened or darkened automatically).
  Changes preview live; **Cancel** puts the old theme back. **EXPORT...** / **IMPORT...** save and load a custom theme as a file.
* Colours can be typed as `#rrggbb` or picked with the colour dialog.

### "Done" sound (Settings > Sound)

* On/off switch, four built-in chimes (sparkle, bell, pop, fanfare - generated on the spot, no audio files shipped),
  volume, and **TEST SOUND**.
* **Use my own audio clip instead of the built-in sound**: BROWSE... for any audio file (CLEAR goes back to the built-in one).
  A plain WAV is used as it is; MP3/OGG/M4A/FLAC etc. are converted once with ffmpeg (so ffmpeg must be found) and trimmed to
  20 seconds. If the file cannot be used, the built-in chime plays instead.
* It plays once, after the whole queue finishes and at least one clip succeeded. It stays quiet if you pressed Stop.

### Subject Marker (Hint > mode "Subject Marker (click it)")

Click on the person/object you want to keep and CorridorKey 2.0 is told to key that one. Your clicks (left = keep,
right = remove) seed OpenCV GrabCut on the **first frame that will be processed**; the result is saved as a soft hint image and
passed with `--hint_first_frame`, the same hint the model already understands. **Grow/shrink** and **Softness** sliders
adjust the edge before it is saved. Press **PLACE MARKERS**, then click in the viewer. UNDO removes the last click, CLEAR removes all,
GO TO FRAME jumps to the frame the markers apply to.

It is a **rough hint, not a hard cut**. The model treats the hint as guidance and may still keep or drop things near it,
and GrabCut struggles with hair, motion blur and subjects the same colour as their surroundings - add a few more clicks
(right-click for "this is background") when that happens. It only affects the first processed frame, because that is what
`infer.py` accepts; the model carries it forward. If you need exact control over every frame, make your own hint video and use
"Hint video".

### More video encoding options (Video Encoding)

Quick **profiles** (README default, High quality, Small files, Compatible 8-bit, H.265), plus codec, **rate control**
(constant quality CRF *or* target bitrate such as `50M`), preset, pixel format (adds 4:2:2 and 4:2:0 choices), ffmpeg
**threads**, and the **frame rate** used for numbered-frame folders. The profile menu shows "Custom" as soon as you change a
value. Hover the pixel format to see which formats play in common players: 4:4:4 10-bit keeps the most colour detail but many
players and editors cannot open it - pick "Compatible 8-bit" for those.

### Send results to Nuke / After Effects

CorridorKey 2.0 is also sold as a Nuke and After Effects plug-in. This GUI is not that plug-in, but File > **Send Results to Nuke
(.nk)** / **After Effects (.jsx)** writes a small script next to your results that sets the shot up for you:

* **Nuke**: open or paste the `.nk` into the Node Graph - it creates a Read node for each FG/matte/comp/cutout output you made
  (set to start at the frame the run began), a Premult after the cutout, and a sticky note saying how to Merge the cutout over
  your background. It deliberately creates no multi-input nodes, so nothing can end up wired wrongly.
* **After Effects**: run the `.jsx` with File > Scripts > Run Script File - it imports the outputs into a project folder and makes a
  comp (right size, frame rate and start offset). If you made a Cutout it goes in the comp as is; otherwise the FG goes in with the
  Matte as its luma track matte (the matte layer is hidden).

These scripts are written from the documented `.nk` and ExtendScript formats. **They have not been run inside Nuke or After
Effects by the author**, so treat them as a convenience that might need a small fix in your version. Both only create
nodes/layers; they never touch your files.

## Panel -> command line

| Section | Controls | infer.py flags |
|---|---|---|
| Hint | mode (none / first frame / video / subject marker), file, quality, carry quality, authoritative | `--hint_first_frame` `--hint_video` `--hint_quality` `--carry_hint_quality` `--no_carry_hint` |
| Subject marker | clicks, grow/shrink, softness | writes a hint image, then `--hint_first_frame` |
| Inference | colour space, despill, cutout linear, model scale | `--frame_dir_linear` `--despill_strength` `--cutout_linear` `--model_scale` |
| GPU Memory | Auto / Manual, Hann window, low-VRAM, cache folder, stage-2 batch | none (auto) or `--hann_chunk` `--hann_stride` `--low_vram` `--temp_dir` `--stage2_batch` |
| Frame Range | frame limit, start, seed | `--num_frames` `--start_mode` `--seed` |
| Output | FG / Matte / Comp / Cutout, video or EXR, EXR type | `--outputs` `--output_format` `--exr_dtype` |
| Video Encoding | profile, codec, CRF or bitrate, preset, pixel format, threads, frame rate | `--ffmpeg_codec` `--crf` `--bitrate` `--preset` `--pix_fmt` `--ffmpeg_threads` `--frame_dir_fps` |

A bitrate replaces CRF in the runtime, so the GUI sends one or the other, never both. The exact command for every job is
printed at the top of its log (F12).

## Privacy, and files the GUI keeps

The window makes no network connections and sends nothing anywhere. `%APPDATA%\CorridorKey2-GUI\` (Linux:
`~/.config/CorridorKey2-GUI/`, macOS: `~/Library/Application Support/`) holds the session (including the paths of the clips you
imported), preferences, generated subject-marker hints (`hints\`), cached chimes and converted custom sound (`sounds\`) and
`crash.log`. Settings > General > Settings folder > **OPEN** opens it. Deleting it only resets the GUI; your clips and results
are elsewhere.

**Reporting a bug without leaking yourself:** use Help > System Check > **COPY FOR A BUG REPORT**, or attach `crash.log`. Both
have your account name replaced by `<user>` in every folder path. File and clip names are not changed, so skim before pasting.

## Differences from the Corridor Key 1 GUI (on purpose)

* No alpha generators, paint masks or live preview: CorridorKey 2.0 takes optional hint mattes instead and runs as a
  streaming video pipeline, so there is no per-frame re-process to preview. (The Subject Marker is the closest thing: it builds the
  hint for you.)
* No in/out markers: 2.0 only has `--num_frames` / `--start_mode`. The scrubber shows the frames that will be processed (yellow
  bracket) and the frames that have outputs (yellow line).
* Viewer previews are 8-bit display images decoded with OpenCV. EXR outputs are tone-mapped with the sRGB curve for display only.
  Files on disk are never modified.
* Each job reloads the model (as the CLI does), so batches pay the load time per clip.

## What was and was not verified

* **Design sources:** the extra features (hover help, encoding options, Nuke/After Effects hand-off) were derived from the
  CorridorKey README, `infer.py`'s real flags and the public product description, not from the plug-in itself.
* **Tested (Linux, no GPU):** every GUI command parses in the real `infer.py`; the window runs against a fake `infer.py`; theme, help,
  sound, subject-marker, privacy-scrubbing and export code have their own tests; the launcher logic has its own test.
* **Used for real:** the launcher and the window were run on the author's Windows PC.
* **Not tested by the author:** the standalone exe on Windows (CI builds it and runs `--selftest`), audio on every sound card, and the
  Nuke/After Effects scripts inside those apps.

## Tests (no GPU needed)

Run these from your CorridorKey folder (the first one needs the real `infer.py`):

```
python tests/test_command_vs_infer.py   # every GUI command parses in the real infer.py; re-run after updating infer.py
python tests/test_gui_offscreen.py      # drives the real window offscreen against tests/fake_infer.py
python tests/test_gui_features.py       # themes, help, sound, subject marker, encoding, About, Nuke/AE export in the real window
python tests/test_modules.py            # the new modules on their own (subject, sound, exports, help, theme maths, scrub)
python run_gui.py --selftest            # quick health check (also works on the frozen exe)
```

The launcher exe's logic has its own Linux-only test in `launcher/test/` (see the README.txt there).

## License

Corridor Key Licence 2.0 (CC BY-NC-SA 4.0 plus Corridor Digital's additional terms) - see `LICENSE`. Free to use, including
commercially, but it may not be sold or offered as a paid service, anything you release must stay free under the same licence and
keep the CorridorKey name prominent, and organisations above US$20M annual revenue need the plug-in seat (corridorkey.com).
