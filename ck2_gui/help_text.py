"""Plain-language help for every section and control (shown as tooltips next to the mouse).

Written for people who have never keyed footage before, but without talking down. The facts come from
the CorridorKey README (section names are given as "README: ..." so you can read the long version).
Qt-free: only strings and small helper functions, so it can be tested anywhere.
"""
from __future__ import annotations

from html import escape

ENABLED = True        # the Settings dialog can turn hover help off


# --------------------------------------------------------------------------
# per-control help: key -> (title, what it does, extra tip, README section)
# --------------------------------------------------------------------------
HELP: dict[str, tuple[str, str, str, str]] = {
    # ---- HINT ------------------------------------------------------------
    "hint_mode": (
        "Hint mode",
        "How you tell the AI which thing in the shot to keep. "
        "No Hint: the AI picks the subject itself (fast, fine for simple shots). "
        "Subject Marker: you click the person or object you want and the app builds the hint for you. "
        "First-Frame Hint: you supply one black-and-white image for the first frame and the AI follows that subject. "
        "Full Hint Video: you supply a black-and-white matte for every frame (most control).",
        "Several people or objects in frame? Use Subject Marker or a hint, otherwise the AI may choose the wrong one.",
        "Choosing An Inference Mode"),
    "hint_path": (
        "Hint file",
        "The black-and-white picture, video or folder of frames that marks your subject. "
        "White means keep, black means throw away. A single-channel image, or an image with an alpha channel, both work.",
        "It does not have to be perfect. It only has to point at the right subject; the AI cleans up edges and fine detail.",
        "First-Frame Hint"),
    "hint_quality": (
        "Hint quality",
        "How much the AI should trust your hint. 0.95 is for a clean, hand-made matte. "
        "0.75 is for a rough or automatic hint (the Subject Marker starts here). "
        "0.50 or lower is for a loose scribble or an unreliable source.",
        "This does not change your hint image. It only changes how strongly the AI listens to it.",
        "Hint Quality"),
    "carry_quality": (
        "Carry quality",
        "After your hint, the AI keeps passing its own best matte forward as a new hint so the key stays steady over "
        "time. This sets how much it trusts that carried matte (default 0.95).",
        "Leave it at 0.95 unless the matte starts drifting onto the wrong thing.",
        "Hint Quality"),
    "no_carry": (
        "Hint is authoritative",
        "Use your hint video exactly as given on every frame, and do not let the AI feed its own guesses back in. "
        "Choose this when your hint is trustworthy (for example hand-painted roto). Full Hint Video only.",
        "Trade-off: you give up one of the tricks that keeps the matte stable, so a flickery hint gives a flickery result.",
        "Full Hint Video Without Carry"),
    "marker": (
        "Subject marker",
        "Left-click the thing you want to keep. Right-click something you want removed. Add as many clicks as you need. "
        "The app makes a rough cut-out from your clicks (it looks at colour, so clicks on a few different parts of the "
        "subject help). The AI then uses that as a starting hint and tracks the subject through the clip.",
        "Markers go on the first frame that will be processed. It is a strong hint, not a hard cut: the AI still decides "
        "the fine detail like hair, and in long or crowded shots it can drift (see Hint Quality).",
        "First-Frame Hint"),
    "marker_grow": (
        "Grow / shrink",
        "Makes the rough cut-out a little bigger (positive) or smaller (negative). Use it if the selection is slightly "
        "too tight or too loose around the subject.",
        "A hint that is too eroded or too dilated nudges the final result the same way, so aim for 'about right'.",
        "Full Hint Video"),
    "marker_soft": (
        "Edge softness",
        "Blurs the edge of the rough cut-out. A soft edge is a more forgiving hint, which is usually what you want for "
        "hair and motion blur.",
        "",
        "Hint Quality"),

    # ---- INFERENCE -------------------------------------------------------
    "space": (
        "Input colour space",
        "Tells the AI how to read the pixel values of a frame folder. sRGB is normal video and photos. "
        "Linear is for scene-linear image sequences such as EXR plates from a VFX pipeline.",
        "Wrong choice = colours look too dark or too bright, and bright EXR highlights get clipped. "
        "Video files are always read as sRGB / Rec.709.",
        "Input Color Handling"),
    "despill": (
        "Despill",
        "Spill is the green (or blue) glow a screen leaves on edges, hair and skin. Despill pulls that tint out. "
        "0 is none, 1 is full.",
        "Only the Comp and Cutout outputs are despilled; the plain FG output is left untouched. Default is 0.5.",
        "Despill Strength"),
    "cutout_linear": (
        "Cutout as straight linear RGB",
        "Changes how the Cutout stores colour. Off: straight sRGB, which looks right on screen. "
        "On: straight scene-linear, which is what linear compositing workflows usually want.",
        "EXR output is always linear, so this only matters for video Cutouts.",
        "Cutout Linear"),
    "model_scale": (
        "Model scale",
        "Resizes the picture before the AI sees it. 1.0 is the clip's own (native) resolution. "
        "Lower values mean fewer pixels for the AI to look at, which is lighter on memory but gives it less fine detail "
        "to work with.",
        "Leave it at 1.0 unless you are testing or short on memory.",
        "infer.py --model_scale"),

    # ---- GPU MEMORY ------------------------------------------------------
    "profile": (
        "Memory mode",
        "Auto measures how much graphics-card memory (VRAM) is free for each clip and picks the biggest settings that "
        "fit. Manual lets you choose the Hann window yourself.",
        "If you ever see a 'CUDA out of memory' error, switch to Manual and pick a smaller window or turn on Low-VRAM.",
        "Long Clips And Low VRAM"),
    "hann": (
        "Hann window (time awareness)",
        "The AI studies groups of neighbouring frames together so the matte does not flicker. That is its 'time "
        "awareness'. A bigger group means a steadier matte but more VRAM. 80 / 40 is the biggest; "
        "1 / 1 looks at every frame alone (no time awareness) and uses the least memory.",
        "The two numbers are 'frames per group / how far the group moves each step'. Half overlap blends the seams.",
        "Hann Windows"),
    "chunk": (
        "Chunk",
        "How many frames are studied together in one group.",
        "", "Hann Windows"),
    "stride": (
        "Stride",
        "How far the group moves forward each step. Half of the chunk gives a 50% overlap so neighbouring groups blend "
        "smoothly. It can never be bigger than the chunk.",
        "", "Hann Windows"),
    "low_vram": (
        "Low-VRAM mode",
        "Does the work in stages and keeps temporary data on disk instead of in graphics memory. "
        "It is slower and uses more disk, but lets long or high-resolution clips run on smaller cards.",
        "The result is the same kind of exact result, just reached in a more memory-friendly way.",
        "Long Clips And Low VRAM"),
    "temp": (
        "Feature cache folder",
        "Where Low-VRAM mode stores its temporary files. Pick a drive with plenty of free space (several GB).",
        "Empty means your system temp folder.",
        "Long Clips And Low VRAM"),
    "stage2": (
        "Stage 2 batch",
        "How many final-size frames are finished at the same time. 1 uses the least memory and was no slower in the "
        "developers' tests.",
        "Leave this at 1 unless you know why you are changing it.",
        "Long Clips And Low VRAM"),

    # ---- FRAME RANGE -----------------------------------------------------
    "limit": (
        "Frame limit",
        "Process only this many frames. 0 means the whole clip. Great for testing settings quickly before you commit "
        "to a long render.",
        "", "Partial Clips"),
    "start": (
        "Start",
        "Where the test segment is taken from: the start of the clip, the middle, or a repeatable random spot in the "
        "middle. Frame folders always use their first frames.",
        "The viewer's scrub bar shows a bracket around the frames that will be processed.",
        "Partial Clips"),
    "seed": (
        "Seed",
        "The number that picks the 'random middle' segment. The same number always gives the same segment.",
        "", "Partial Clips"),

    # ---- OUTPUT ----------------------------------------------------------
    "out_alpha": (
        "Matte (alpha)",
        "A black-and-white picture of how much of each pixel belongs to the subject: white is solid, grey is "
        "see-through (hair, glass, motion blur), black is background.",
        "", "Outputs"),
    "out_fg": (
        "FG (foreground)",
        "The subject's own colours with the screen colour removed from see-through areas. "
        "Use it together with the Matte in your compositing app.",
        "", "Outputs"),
    "out_checker": (
        "Comp (checkerboard)",
        "A review render: the subject over a checkerboard, with despill applied. The quickest way to judge a key.",
        "Extra outputs cost extra rendering time, so tick this for review renders only.",
        "Outputs"),
    "out_cutout": (
        "Cutout",
        "The subject with its matte already built in as transparency: ProRes 4444 with alpha for video, or an RGBA EXR. "
        "Ready to drop on a new background.",
        "", "Outputs"),
    "fmt": (
        "Output format",
        "Video previews are ordinary video files, clipped to the normal 0-1 range. "
        "EXR sequence writes one floating-point image per frame in linear colour and keeps bright highlights "
        "(HDR) - the VFX-grade choice.",
        "The Video Encoding section only applies to Video previews.",
        "HDR EXR Output"),
    "exr_dtype": (
        "EXR type",
        "Half (16-bit) is the VFX standard and plenty. Float (32-bit) makes files about twice as big without adding "
        "accuracy the model actually produces.",
        "", "HDR EXR Output"),
    "out_dir": (
        "Output folder",
        "Where this clip's results are written. Empty means a folder called out_<clip name> next to the clip.",
        "", "Outputs"),

    # ---- VIDEO ENCODING --------------------------------------------------
    "enc_profile": (
        "Quick profile",
        "One-click starting points. Review = the README defaults (near-lossless 10-bit). High = even better, bigger "
        "files. Small = much smaller files. Compatible = 8-bit 4:2:0 that plays on nearly everything. "
        "H.265 = smaller files with modern players.",
        "Picking one just fills in the boxes below; you can still tweak them.",
        "Video Encoding"),
    "codec": (
        "Codec",
        "The compression method. libx264 (H.264) plays almost everywhere. libx265 (H.265) makes smaller files but "
        "some software cannot open it. You can type any codec your ffmpeg has.",
        "The Cutout always uses ProRes 4444 so it keeps its transparency, whatever you choose here.",
        "Video Encoding"),
    "rate_mode": (
        "Rate control",
        "Quality (CRF) keeps the picture quality steady and lets the file size vary. "
        "Bitrate fixes the amount of data per second and lets quality vary.",
        "For keying review files, Quality (CRF) is usually the better choice.",
        "Video Encoding"),
    "crf": (
        "CRF (quality)",
        "The quality knob: lower is better quality and bigger files. 12 is near-lossless (the default), "
        "18 looks great for most uses, 23 and above is visibly softer.",
        "Ignored when a bitrate is set.",
        "Video Encoding"),
    "bitrate": (
        "Bitrate",
        "A fixed data rate, for example 50M (50 megabits per second) or 8000k. When set, it replaces the CRF quality "
        "setting.",
        "", "Video Encoding"),
    "preset": (
        "Preset",
        "How hard the encoder works to shrink the file. Slower presets give smaller files at the same quality but take "
        "longer. 'medium' is a good balance.",
        "", "Video Encoding"),
    "pix_fmt": (
        "Pixel format",
        "How colour is stored. yuv444p10le (default) keeps full colour detail in 10-bit. yuv444p is 8-bit and plays in "
        "more places. yuv422p10le and yuv420p10le are 10-bit with less colour detail (smaller files). yuv420p is the "
        "most compatible 8-bit format (phones, browsers) but throws away most colour detail, which can soften edges "
        "around a keyed subject.",
        "Use yuv444p if a playback target needs 8-bit H.264.",
        "Video Encoding"),
    "threads": (
        "ffmpeg threads",
        "How many CPU threads ffmpeg may use while encoding (default 2). More can speed up encoding on a strong CPU.",
        "", "Video Encoding"),
    "frame_fps": (
        "Frame rate (frame folders)",
        "A folder of images has no frame rate of its own, so this sets the rate used when videos are written from it.",
        "", "Frame Directories"),
}

# --------------------------------------------------------------------------
# section overviews (shown when you hover the section header)
# --------------------------------------------------------------------------
SECTIONS: dict[str, dict] = {
    "HINT": {
        "title": "Hint",
        "intro": "A hint is a rough black-and-white picture that shows the AI which thing in your shot is the subject: "
                 "white means keep, black means throw away. Without one, the AI decides for itself - fine for simple "
                 "shots, but with several people in frame it can pick the wrong one. A hint does not need to be perfect; "
                 "the AI cleans up the edges and the fine detail.",
        "readme": "Choosing An Inference Mode, Hint Quality",
        "params": ["hint_mode", "marker", "hint_path", "hint_quality", "carry_quality", "no_carry"],
    },
    "INFERENCE": {
        "title": "Inference",
        "intro": "How the footage is read and how the finished foreground is cleaned up. These settings change how the "
                 "result looks, not how long it takes (except Model scale).",
        "readme": "Input Color Handling, Despill Strength, Cutout Linear",
        "params": ["space", "despill", "cutout_linear", "model_scale"],
    },
    "GPU MEMORY": {
        "title": "GPU memory",
        "intro": "How the work is split up so it fits in your graphics card's memory (VRAM). Auto is right for almost "
                 "everyone. The AI looks at several frames at once - its 'time awareness' - so the matte does not "
                 "flicker; these settings trade memory for that smoothness.",
        "readme": "Hann Windows, Long Clips And Low VRAM",
        "params": ["profile", "hann", "low_vram", "temp", "stage2"],
    },
    "FRAME RANGE": {
        "title": "Frame range",
        "intro": "Run only part of a clip so you can test your settings quickly before committing to the whole thing.",
        "readme": "Partial Clips",
        "params": ["limit", "start", "seed"],
    },
    "OUTPUT": {
        "title": "Output",
        "intro": "Which result files are written and in what format. Every extra output costs rendering and encoding "
                 "time, so tick only what you need. Matte and FG are the 'real' results; Comp and Cutout are "
                 "convenient extras.",
        "readme": "Outputs, HDR EXR Output",
        "params": ["out_alpha", "out_fg", "out_checker", "out_cutout", "fmt", "exr_dtype", "out_dir"],
    },
    "VIDEO ENCODING": {
        "title": "Video encoding",
        "intro": "How the result videos are compressed by ffmpeg. This only applies to the 'Video previews' format; EXR "
                 "sequences ignore it. The defaults are already high quality, so change these only for a reason such as "
                 "smaller files or wider playback support.",
        "readme": "Video Encoding",
        "params": ["enc_profile", "codec", "rate_mode", "crf", "bitrate", "preset", "pix_fmt", "threads", "frame_fps"],
    },
}

# --------------------------------------------------------------------------
# tips for the rest of the window
# --------------------------------------------------------------------------
UI: dict[str, tuple[str, str]] = {
    "brand": ("CorridorKey 2.0",
              "An unofficial desktop front-end for CorridorKey 2.0, the AI green/blue-screen keyer by Corridor Digital. "
              "This window only builds the command and shows the results; the official CorridorKey runtime does all the keying."),
    "gpu": ("Graphics card", "The NVIDIA graphics card CorridorKey will use. It needs CUDA; the name comes from "
                             "nvidia-smi."),
    "vram": ("VRAM meter", "How much of your graphics card's memory is in use right now. If it hits the red end during a "
                           "run, you may get an out-of-memory error: try a smaller Hann window or Low-VRAM mode."),
    "settings": ("Settings", "Folders, theme, completion sound and help options."),
    "queue": ("Queue", "Clips waiting to run, in order. Only one clip runs at a time. The cross removes a waiting clip."),
    "tray_in": ("Input clips", "Everything you have imported. Click a clip to work on it, Ctrl-click or Shift-click for "
                               "several, right-click for more actions."),
    "tray_out": ("Exports", "Clips that finished. Double-click one to open its output folder."),
    "card": ("Clip", "Click to select. Double-click to open its output folder. Right-click for more."),
    "progress": ("Progress", "How far the current job has got."),
    "run": ("Run inference", "Key the selected clip(s) with the settings on the right. Ctrl+R."),
    "run_all": ("Run all", "Queue every clip that is ready (and any that failed or were cancelled). Ctrl+Shift+R."),
    "stop": ("Stop", "Cancel the running job and everything still waiting. Esc."),
    "scrub": ("Timeline", "Click or drag to change frame. The bright line on top shows frames that already have results; "
                          "the line underneath shows where a hint exists; a bracket marks the frames that will be "
                          "processed when a frame limit is set."),
    "zoom": ("Zoom", "Mouse wheel zooms at the cursor, drag to pan, double-click to reset. Both views stay in sync."),
    "tab_input": ("INPUT", "Your original footage."),
    "tab_hint": ("HINT", "The black-and-white hint the AI will use (greyed out when there is none)."),
    "tab_fg": ("FG", "The foreground colours with the screen colour removed. Available after a run."),
    "tab_alpha": ("MATTE", "The black-and-white matte (white = subject). Available after a run."),
    "tab_checker": ("COMP", "The subject over a checkerboard with despill - the quick review view."),
    "tab_cutout": ("PROC", "The Cutout: subject with transparency built in, shown over a checkerboard."),
    "apply_all": ("Apply to all clips", "Copy these settings to every other clip. Each clip keeps its own hint, colour "
                                        "space, frame rate and output folder."),
}


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def _wrap(inner: str, width: int = 340) -> str:
    return f'<table width="{width}" cellpadding="0" cellspacing="0"><tr><td>{inner}</td></tr></table>'


def control_tip(key: str, now: str = "") -> str:
    """Tooltip for one setting. `now` is the "what does the current value mean" sentence (see dynamic())."""
    if key not in HELP:
        return ""
    title, what, extra, readme = HELP[key]
    parts = [f'<p style="margin:0 0 4px 0"><b>{escape(title)}</b></p>',
             f'<p style="margin:0 0 4px 0">{escape(what)}</p>']
    if extra:
        parts.append(f'<p style="margin:0 0 4px 0"><i>{escape(extra)}</i></p>')
    if now:
        parts.append(f'<p style="margin:0 0 4px 0"><b>Right now:</b> {escape(now)}</p>')
    if readme:
        parts.append(f'<p style="margin:2px 0 0 0"><small>README: {escape(readme)}</small></p>')
    return _wrap("".join(parts))


def section_tip(name: str) -> str:
    sec = SECTIONS.get(name)
    if sec is None:
        return ""
    items = []
    for k in sec["params"]:
        t, what, _x, _r = HELP[k]
        first = what.split(". ")[0].rstrip(".")
        items.append(f"<li><b>{escape(t)}</b> - {escape(first)}.</li>")
    inner = (f'<p style="margin:0 0 4px 0"><b>{escape(sec["title"].upper())}</b></p>'
             f'<p style="margin:0 0 4px 0">{escape(sec["intro"])}</p>'
             f'<p style="margin:0 0 2px 0"><b>The settings in this section</b> (hover each for the full story):</p>'
             f'<ul style="margin:0 0 4px 0">{"".join(items)}</ul>'
             f'<p style="margin:2px 0 0 0"><small>README: {escape(sec["readme"])}</small></p>')
    return _wrap(inner, 380)


def ui_tip(key: str) -> str:
    if key not in UI:
        return ""
    title, body = UI[key]
    return _wrap(f'<p style="margin:0 0 4px 0"><b>{escape(title)}</b></p><p style="margin:0">{escape(body)}</p>', 300)


# --------------------------------------------------------------------------
# "what does this value mean right now" sentences
# --------------------------------------------------------------------------
def dynamic(key: str, value) -> str:
    try:
        if key == "hint_quality" or key == "carry_quality":
            v = float(value)
            if v >= 0.9:
                return f"{v:.2f} - high trust. The AI follows the hint closely (right for a clean, hand-made matte)."
            if v >= 0.7:
                return f"{v:.2f} - medium trust. Good for a rough or automatic hint."
            if v > 0.45:
                return f"{v:.2f} - low trust. The hint is treated as a suggestion."
            return f"{v:.2f} - very low trust. The hint barely steers the result."
        if key == "despill":
            v = float(value)
            if v <= 0.0:
                return "0.00 - no despill. Green spill stays in Comp and Cutout."
            if v < 0.35:
                return f"{v:.2f} - light despill. Removes only the strongest green tint."
            if v < 0.7:
                return f"{v:.2f} - medium despill (the default area). Balanced for most shots."
            return f"{v:.2f} - strong despill. Cleans edges well but can slightly shift skin and hair colours."
        if key == "model_scale":
            v = float(value)
            if abs(v - 1.0) < 1e-6:
                return "1.00 - full resolution. Best detail."
            return (f"{v:.2f} - the picture is {'shrunk' if v < 1 else 'enlarged'} before the AI sees it. "
                    + ("Lighter on memory, with less fine detail for the AI to work with." if v < 1 else
                       "Heavier on memory and time."))
        if key == "crf":
            v = int(value)
            if v <= 8:
                return f"CRF {v} - virtually lossless, very large files."
            if v <= 14:
                return f"CRF {v} - near-lossless review quality (the default is 12)."
            if v <= 20:
                return f"CRF {v} - excellent quality, noticeably smaller files."
            return f"CRF {v} - visibly softer, small files."
        if key == "hann":
            chunk, stride = value
            if chunk <= 1:
                return "Each frame is keyed on its own: least memory, but no time awareness, so the matte may flicker."
            return (f"Groups of {chunk} frames, moving {stride} at a time ({round(100 * (1 - stride / chunk))}% overlap). "
                    + ("Maximum continuity, needs a lot of VRAM." if chunk >= 80 else
                       "Good balance of steadiness and memory." if chunk >= 24 else
                       "Light on memory; shorter-range steadiness."))
        if key == "limit":
            v = int(value)
            return "The whole clip will be processed." if v <= 0 else f"Only {v} frames will be processed."
        if key == "bitrate":
            return "Quality (CRF) is used." if not str(value).strip() else f"Fixed bitrate {value}: CRF is ignored."
        if key == "threads":
            return f"ffmpeg may use {int(value)} CPU thread(s)."
        if key == "hint_mode":
            return {
                "none": "No hint - the AI chooses the subject by itself.",
                "marker": "Subject Marker - click the subject in the INPUT view (left-click keep, right-click remove).",
                "first": "First-Frame Hint - one black-and-white image for the first frame of the range.",
                "video": "Full Hint Video - a black-and-white matte for every frame.",
            }.get(str(value), "")
        if key == "marker_grow":
            v = int(value) / 10.0
            if v == 0:
                return "0.0% - the selection is used as it is."
            return (f"{v:+.1f}% of the frame height - the selection is made {'bigger' if v > 0 else 'smaller'} "
                    "all the way round.")
        if key == "marker_soft":
            v = int(value) / 10.0
            return f"{v:.1f}% of the frame height - " + ("a crisp edge." if v < 0.3 else
                                                         "a gentle edge (a good default)." if v < 1.5 else
                                                         "a very soft, forgiving edge.")
        if key == "fmt":
            return ("Video files are written (the Video Encoding settings apply)." if value == "video" else
                    "EXR frames are written; the Video Encoding section is ignored.")
        if key == "profile":
            return ("Auto - the app measures free VRAM for each clip." if value else
                    "Manual - the Hann window and Low-VRAM settings below are used as you set them.")
        if key == "rate_mode":
            return ("Quality (CRF) - steady quality, file size varies." if value == "crf" else
                    "Fixed bitrate - steady file size, quality varies.")
        if key == "pix_fmt":
            v = str(value)
            return ("10-bit, full colour detail." if "10le" in v and "444" in v else
                    "10-bit, colour detail halved or reduced (4:2:2 / 4:2:0)." if "10le" in v else
                    "8-bit, full colour detail." if "444" in v else
                    "8-bit, colour detail halved (4:2:2 / 4:2:0) - the most compatible." if v else "")
    except (TypeError, ValueError):
        return ""
    return ""


# Quick encoding profiles: name -> (codec, crf, preset, pix_fmt)
ENC_PROFILES = {
    "Review (README default)": ("libx264", 12, "medium", "yuv444p10le"),
    "High quality": ("libx264", 8, "slow", "yuv444p10le"),
    "Small files": ("libx264", 20, "fast", "yuv444p"),
    "Compatible 8-bit (plays everywhere)": ("libx264", 16, "medium", "yuv420p"),
    "H.265 (smaller, modern players)": ("libx265", 16, "medium", "yuv444p10le"),
}
