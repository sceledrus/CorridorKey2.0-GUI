#!/usr/bin/env bash
# CorridorKey 2.0 launcher. Optionally drag a clip or folder onto this file.
cd "$(dirname "$0")" || exit 1

if [ -x "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="python3"
fi

"$PYTHON" run_gui.py "$@"
