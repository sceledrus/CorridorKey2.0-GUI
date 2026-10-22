"""CorridorKey 2.0 - a desktop GUI for CorridorKey 2.0 (Corridor Digital).

A PySide6 front-end for ``infer.py``. The GUI never imports torch or the
CorridorKey runtime itself: it builds the same command line that
``run_interactive.py`` builds and runs it as a subprocess, so the model's
behaviour is exactly what the official CLI produces.
"""

__version__ = "0.3.0"
APP_NAME = "CorridorKey 2.0"
AUTHOR_NAME = "Sceledrus"
AUTHOR_URL = "https://www.youtube.com/channel/UCfbv9irTqrpZehCk8V4OvZQ"     # opened in the browser only when clicked
CREDIT_MODEL = "Claude Sonnet 5.5"
