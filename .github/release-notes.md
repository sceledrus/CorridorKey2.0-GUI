## Install (Windows)

1. Set up **CorridorKey 2.0** first (NVIDIA GPU, CUDA PyTorch, weights, ffmpeg) - follow its own README.
2. Download **`CorridorKey2-*-launcher.zip`** below and extract it **into your CorridorKey folder** (the one with `infer.py`).
3. Double-click **`CorridorKey2.exe`**.

Prefer a window that doesn't need Python to open? Use **`CorridorKey2-*-standalone-win64.zip`** instead (also extract it inside your
CorridorKey folder; the AI model still runs in your CorridorKey Python environment).

Windows will say "Windows protected your PC" because the files are not code-signed: **More info > Run anyway**.

## Verify your download

`SHA256SUMS.txt` lists the SHA-256 of each zip. In PowerShell: `Get-FileHash .\CorridorKey2-*-launcher.zip -Algorithm SHA256`.
These files were built by GitHub Actions from the tagged source in this repository.

## Good to know

- Pre-release: the Nuke / After Effects scripts have not been run inside those apps, and the Subject Marker is a rough hint, not a hard cut.
- No telemetry, no network access from the window. See the README for the full privacy notes.
- Unofficial: not affiliated with or endorsed by Corridor Digital.
