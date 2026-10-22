"""Main window: layout and behaviour. Mirrors the Corridor Key 1 GUI structure
(brand bar, queue rail, dual viewer, parameter panel, scrubber, I/O tray,
status bar) with panels adapted to what CorridorKey 2.0 actually offers."""
from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import APP_NAME, AUTHOR_NAME, AUTHOR_URL, CREDIT_MODEL, __version__
from . import exports
from . import help_text as H
from . import sound as SND
from . import sources
from . import subject
from . import theme as T
from .media import MODES, ClipMedia
from .model import (REPO_ROOT, Clip, Settings, build_command, config_dir, default_output_dir, scrub,
                    discover_outputs, find_python, load_session, preflight, processed_range,
                    raw_clip_name, resolve_import, save_session, validate)
from .params import ParamPanel
from .settings_dialog import DEFAULT_PREFS, SettingsDialog, normalised_custom
from .runner import GpuMonitor, JobRunner
from .viewer import ViewerPanel, qimage_from_rgb
from .widgets import BrandBar, QueuePanel, Scrubber, StatusBar, Tray


def fmt_time(sec: Optional[float]) -> str:
    if sec is None:
        return ""
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class _TipGate(QObject):
    """Swallows tooltips of the main window when "hover help" is switched off in Settings."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window_ = window

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.ToolTip and not H.ENABLED and isinstance(obj, QWidget):
            if obj.window() is self.window_:
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self, restore: bool = True, infer_script: str = "", python: str = ""):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1500, 860)
        self.setMinimumSize(1120, 700)
        self.setAcceptDrops(True)

        self.clips: list[Clip] = []
        self.thumbs: dict[str, QPixmap] = {}
        self.selected: list[str] = []
        self.current: Optional[Clip] = None
        self.media: Optional[ClipMedia] = None
        self._sig = None
        self.prefs: dict = dict(DEFAULT_PREFS)
        self._skip_overwrite_prompt = False
        self.infer_script_override = infer_script
        self.python_override = python
        self._batch_done = 0               # clips that finished OK since the queue last went idle
        self._batch_stopped = False        # the user pressed Stop
        self._marker_overlay = None        # RGBA tint of the current clip's subject marker matte
        self._marker_sig = None
        self.sound = SND.SoundPlayer(str(config_dir() / "sounds"))

        restored: list[Clip] = []
        if restore:                         # prefs first: the theme and hover-help setting apply to the whole UI
            restored, prefs = load_session()
            self.prefs.update(prefs)
        self._apply_prefs()
        app = QApplication.instance()
        if app is not None:
            self._tip_gate = _TipGate(self)
            app.installEventFilter(self._tip_gate)

        self.runner = JobRunner(REPO_ROOT, self)
        self.gpu = GpuMonitor(parent=self)
        self._marker_timer = QTimer(self)
        self._marker_timer.setSingleShot(True)
        self._marker_timer.setInterval(120)
        self._marker_timer.timeout.connect(self._marker_regenerate)
        self._build_ui()
        self._build_menus()
        self._build_shortcuts()

        self.runner.changed.connect(self._on_runner_changed)
        self.runner.jobStarted.connect(self._on_job_started)
        self.runner.jobProgress.connect(self._on_job_progress)
        self.runner.jobFinished.connect(self._on_job_finished)
        self.runner.logLine.connect(self._on_log_line)
        self.runner.allDone.connect(self._on_all_done)
        self.gpu.updated.connect(self.brand.set_gpu)

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._play_tick)

        for c in restored:
            self._add_clip(c, select=False)
        if self.clips:
            self.select_clip(self.clips[0].id)
        self._refresh_all()
        self.gpu.start()

    # ------------------------------------------------------------------ paths
    @property
    def python(self) -> str:
        return self.python_override or self.prefs.get("python") or find_python()

    @property
    def infer_script(self) -> str:
        return (self.infer_script_override or os.environ.get("CK2_GUI_INFER")
                or self.prefs.get("infer") or str(REPO_ROOT / "infer.py"))

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.brand = BrandBar()
        self.brand.settingsClicked.connect(self.open_settings)
        v.addWidget(self.brand)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.queue = QueuePanel()
        self.queue.removeRequested.connect(self.runner.remove)
        self.queue.clearRequested.connect(self.runner.clear_finished)
        body.addWidget(self.queue)

        center = QVBoxLayout()
        center.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._welcome())
        self.viewer = ViewerPanel()
        self.stack.addWidget(self.viewer)
        center.addWidget(self.stack, 1)
        self.scrub = Scrubber()
        center.addWidget(self.scrub)
        body.addLayout(center, 1)

        self.params = ParamPanel()
        self.params.edited.connect(self._on_params_edited)
        self.params.applyAll.connect(self._apply_to_all)
        self.params.markerModeChanged.connect(self._on_marker_mode)
        self.params.markerUndo.connect(self._marker_undo)
        self.params.markerClear.connect(self._marker_clear)
        self.params.markerGoto.connect(self._marker_goto)
        self.viewer.markerClicked.connect(self._on_marker_click)
        body.addWidget(self.params)
        v.addLayout(body, 1)

        self.tray = Tray()
        self.tray.selected.connect(self._on_card_clicked)
        self.tray.opened.connect(self._reveal_outputs_for)
        self.tray.context.connect(self._card_menu)
        self.tray.addRequested.connect(self.import_dialog)
        v.addWidget(self.tray)

        self.status = StatusBar()
        self.status.runClicked.connect(self.run_selected)
        self.status.runAllClicked.connect(self.run_all)
        self.status.stopClicked.connect(self.stop)
        v.addWidget(self.status)

        self.viewer.zoomChanged.connect(self.scrub.set_zoom)
        self.scrub.frameChanged.connect(self._on_frame)
        self.scrub.playToggled.connect(self._on_play_toggled)

        self.console = QDialog(self)
        self.console.setWindowTitle(APP_NAME + " console")
        self.console.resize(820, 420)
        cl = QVBoxLayout(self.console)
        self.console_text = QPlainTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setMaximumBlockCount(6000)
        self.console_text.setFont(T.mono_font(11))
        cl.addWidget(self.console_text)

    def _welcome(self) -> QWidget:
        w = QWidget()
        T.style_box(w, "welcome", "BG_VIEW")
        l = QVBoxLayout(w)
        l.setAlignment(Qt.AlignCenter)
        l.setSpacing(10)
        t = QLabel("DROP A CLIP, FRAME SEQUENCE OR FOLDER HERE")
        T.sty(t, lambda: f"color:{T.c('TEXT_DIM')}; font-size:14px; font-weight:bold; letter-spacing:3px;")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("MP4 \u00b7 MOV \u00b7 MKV \u00b7 AVI \u00b7 WEBM \u00b7 EXR / PNG / JPG frame folders")
        T.sty(s, lambda: f"color:{T.c('TEXT_FAINT')}; font-size:11px; letter-spacing:1px;")
        s.setAlignment(Qt.AlignCenter)
        b = QPushButton("IMPORT CLIP")
        b.setObjectName("primary")
        b.setFixedWidth(180)
        b.clicked.connect(self.import_dialog)
        b2 = QPushButton("IMPORT FOLDER")
        b2.setFixedWidth(180)
        b2.clicked.connect(self.import_folder_dialog)
        for x in (t, s):
            l.addWidget(x)
        l.addSpacing(14)
        l.addWidget(b, 0, Qt.AlignCenter)
        l.addWidget(b2, 0, Qt.AlignCenter)
        return w

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def act(menu: QMenu, text: str, slot, key=None) -> QAction:
            a = QAction(text, self)
            if key:
                a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        f = mb.addMenu("File")
        act(f, "Import Clip(s)...", self.import_dialog, "Ctrl+O")
        act(f, "Import Frame Sequence Folder...", self.import_sequence_dialog)
        act(f, "Import Folder of Clips...", self.import_folder_dialog)
        f.addSeparator()
        act(f, "Open Output Folder", lambda: self._reveal_outputs_for(self.current.id) if self.current else None)
        act(f, "Send Results to Nuke (.nk)...", lambda: self.export_to("nuke"))
        act(f, "Send Results to After Effects (.jsx)...", lambda: self.export_to("ae"))
        act(f, "Save Session", self.save, "Ctrl+S")
        f.addSeparator()
        act(f, "Quit", self.close, "Ctrl+Q")

        e = mb.addMenu("Edit")
        act(e, "Run Inference on Selected", self.run_selected, "Ctrl+R")
        act(e, "Run All Ready Clips", self.run_all, "Ctrl+Shift+R")
        act(e, "Stop", self.stop, "Esc")
        e.addSeparator()
        act(e, "Remove Selected Clips", self.remove_selected, "Del")
        act(e, "Settings...", self.open_settings, "Ctrl+,")

        v = mb.addMenu("View")
        act(v, "Toggle Queue Panel", lambda: self.queue.set_open(not self.queue.is_open()), "Q")
        for i, (key, label) in enumerate(MODES):
            act(v, f"View: {label}", lambda _=False, k=key: self.viewer.set_mode(k), f"F{i + 1}")
        act(v, "A/B Wipe (input vs result)", self.viewer.toggle_wipe, "A")
        act(v, "Reset Zoom", self.viewer.reset_view, "Ctrl+0")
        act(v, "Toggle Console", self._toggle_console, "F12")

        h = mb.addMenu("Help")
        act(h, "System Check...", self.system_check)
        act(h, "Keyboard Shortcuts", self.show_shortcuts)
        act(h, "About / License", self.about)

    def _build_shortcuts(self) -> None:
        def sc(key, slot):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(slot)
        sc(Qt.Key_Space, lambda: self.scrub._toggle())
        sc(Qt.Key_Left, lambda: self.scrub.go(self.scrub.bar.frame - 1))
        sc(Qt.Key_Right, lambda: self.scrub.go(self.scrub.bar.frame + 1))
        sc(Qt.Key_Home, lambda: self.scrub.go(0))
        sc(Qt.Key_End, lambda: self.scrub.go(self.scrub.bar.count - 1))

    # ------------------------------------------------------------- importing
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.import_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def import_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import clips", "", "Video (*.mp4 *.mov *.mkv *.avi *.webm);;All files (*)")
        self.import_paths(paths)

    def import_sequence_dialog(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Choose a folder of frames (EXR / PNG / JPG)")
        if p:
            self.import_paths([p])

    def import_folder_dialog(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Choose a folder of clips")
        if p:
            self.import_paths([p])

    def import_paths(self, paths: list[str]) -> None:
        added, problems = [], []
        known = {os.path.normpath(c.path) for c in self.clips}
        for path in paths:
            if not path:
                continue
            items = resolve_import(path)
            if not items:
                problems.append(f"{os.path.basename(path) or path}: no supported video or frame sequence found")
            for it in items:
                if os.path.normpath(it.path) in known:
                    continue
                try:
                    info = sources.probe(it.path)
                except Exception as ex:
                    problems.append(f"{os.path.basename(it.path)}: {ex}")
                    continue
                s = Settings(hint_mode=it.hint_mode, hint_path=it.hint_path,
                             frame_linear=it.linear_default and it.kind == "sequence")
                if it.kind == "sequence":
                    s.frame_fps = round(info["fps"], 3) if info["fps"] else 24.0
                clip = Clip(it.path, it.kind, raw_clip_name(it.path), info["frames"], info["fps"],
                            info["width"], info["height"], s)
                if info.get("thumb") is not None:
                    self.thumbs[clip.id] = QPixmap.fromImage(qimage_from_rgb(info["thumb"]).copy())
                self._add_clip(clip, select=False)
                known.add(os.path.normpath(it.path))
                added.append(clip)
        if added:
            self.select_clip(added[0].id)
            hinted = sum(1 for c in added if c.settings.hint_mode != "none")
            msg = f"Imported {len(added)} clip(s)"
            if hinted:
                msg += f", {hinted} with a companion hint detected"
            self.status.message(msg + ".")
        if problems:
            QMessageBox.warning(self, "Import", "\n".join(problems))
        self._refresh_all()

    def _add_clip(self, clip: Clip, select: bool = True) -> None:
        self.clips.append(clip)
        if clip.id not in self.thumbs:
            try:
                info = sources.probe(clip.path)
                if info.get("thumb") is not None:
                    self.thumbs[clip.id] = QPixmap.fromImage(qimage_from_rgb(info["thumb"]).copy())
            except Exception:
                pass
        if select:
            self.select_clip(clip.id)

    def remove_selected(self) -> None:
        ids = set(self.selected) or ({self.current.id} if self.current else set())
        ids = {i for i in ids if not self.runner.queued_for(i)}
        if not ids:
            return
        self.clips = [c for c in self.clips if c.id not in ids]
        if self.current and self.current.id in ids:
            self._close_media()
            self.current = None
            self.selected = []
            if self.clips:
                self.select_clip(self.clips[0].id)
        self.selected = [i for i in self.selected if i not in ids]
        self._refresh_all()

    # ------------------------------------------------------------- selection
    def clip_by_id(self, cid: str) -> Optional[Clip]:
        return next((c for c in self.clips if c.id == cid), None)

    def _on_card_clicked(self, cid: str, mods) -> None:
        if mods & Qt.ControlModifier:
            if cid in self.selected:
                self.selected.remove(cid)
            else:
                self.selected.append(cid)
            self._refresh_tray()
            self._update_run_label()
            return
        if mods & Qt.ShiftModifier and self.current:
            ids = [c.id for c in self.clips]
            a, b = sorted((ids.index(self.current.id), ids.index(cid)))
            self.selected = ids[a:b + 1]
            self._refresh_tray()
            self._update_run_label()
            return
        self.select_clip(cid)

    def select_clip(self, cid: str) -> None:
        clip = self.clip_by_id(cid)
        if clip is None:
            return
        self.play_timer.stop()
        self.scrub.set_playing(False)
        self.selected = [cid]
        self.current = clip
        self._close_media()
        self.media = ClipMedia(clip)
        self.current = clip
        self._scan_outputs(clip)
        self._sig = self._signature(clip)
        self.params.set_settings(clip.settings, clip.kind)
        self.stack.setCurrentIndex(1)
        self.viewer.set_media(self.media, self._info(clip), self._short_info(clip))
        self._marker_load(clip)
        self._update_scrubber()
        self._refresh_tray()
        self._update_run_label()

    def _scan_outputs(self, clip: Clip) -> None:
        """Rescan result files, but never open ones a running job is still writing."""
        if self.media is None or self.current is not clip:
            return
        if clip.status in ("QUEUED", "RUNNING"):
            self.media.scan_outputs("")
        else:
            self.media.scan_outputs(self._out_dir(clip))

    def _close_media(self) -> None:
        if self.media is not None:
            self.media.close()
            self.media = None

    # ----------------------------------------------------------- param edits
    @staticmethod
    def _signature(c: Clip):
        s = c.settings
        return (s.hint_mode, s.hint_path, s.frame_linear, s.frame_fps, s.output_format)

    def _on_params_edited(self) -> None:
        if self.current is None or self.media is None:
            return
        sig = self._signature(self.current)
        old, self._sig = self._sig, sig
        self._marker_params_changed()
        if old and sig != old:
            if old[2:4] != sig[2:4]:
                self.media.reload_input()
            if old[:2] != sig[:2]:
                self.media.reload_hint()
            if old[4] != sig[4]:
                self._scan_outputs(self.current)
            self.viewer.refresh_tabs()
            self.viewer.refresh()
        self._update_scrubber()

    def _apply_to_all(self) -> None:
        if self.current is None:
            return
        src = self.current.settings
        for c in self.clips:
            if c is self.current:
                continue
            keep_hint = (c.settings.hint_mode, c.settings.hint_path)
            keep_marks = (c.settings.markers, c.settings.marker_frame)
            keep_lin = c.settings.frame_linear if c.kind == "sequence" else False
            keep_fps = c.settings.frame_fps
            new = src.copy()
            new.hint_mode, new.hint_path = keep_hint
            new.markers, new.marker_frame = keep_marks
            new.frame_linear, new.frame_fps, new.out_dir = keep_lin, keep_fps, ""
            c.settings = new
        self.status.message(f"Applied these settings to {len(self.clips) - 1} other clip(s) "
                            "(hint files, subject markers, colour space and output folders were kept).")

    # --------------------------------------------------------------- viewing
    def _info(self, c: Clip) -> str:
        return f"{c.frames} frames \u00b7 {c.kind} \u00b7 {c.width}x{c.height}"

    def _short_info(self, c: Clip) -> str:
        return c.status

    def _update_scrubber(self) -> None:
        c, m = self.current, self.media
        if c is None or m is None:
            self.scrub.set_state(0, 0)
            return
        s = c.settings
        plan = None
        if s.num_frames > 0:
            a, n = processed_range(c.frames, c.kind, s)
            plan = (a, a + n)
        done = None
        if m.has_outputs():
            first = next(iter(m.outputs.values()))
            done = (c.ran_start, c.ran_start + first.count)
        hint = s.hint_mode if m.available("hint") else "none"
        self.scrub.set_state(m.count, self.viewer.frame_idx, plan, done, hint)

    def _on_frame(self, f: int) -> None:
        self.viewer.set_frame(f)
        self._marker_view_sync()

    def _on_play_toggled(self, on: bool) -> None:
        if on and self.media is not None and self.media.count > 1:
            fps = min(self.current.fps if self.current else 12, 12) or 12
            self.play_timer.start(int(1000 / fps))
        else:
            self.play_timer.stop()
            self.scrub.set_playing(False)

    def _play_tick(self) -> None:
        if self.media is None or self.media.count <= 1:
            self.play_timer.stop()
            return
        nxt = self.scrub.bar.frame + 1
        if nxt >= self.media.count:
            nxt = 0
        self.scrub.go(nxt)

    # ---------------------------------------------------------------- running
    def _out_dir(self, clip: Clip) -> str:
        return default_output_dir(clip, self.prefs.get("out_dir", ""))

    def _selected_clips(self) -> list[Clip]:
        ids = self.selected or ([self.current.id] if self.current else [])
        return [c for c in self.clips if c.id in ids]

    def run_selected(self) -> None:
        self.run_clips(self._selected_clips())

    def run_all(self) -> None:
        self.run_clips([c for c in self.clips if c.status in ("READY", "ERROR", "CANCELLED")])

    def run_clips(self, clips: list[Clip]) -> None:
        seen: set[str] = set()
        clips = [c for c in clips
                 if not self.runner.queued_for(c.id) and not (c.id in seen or seen.add(c.id))]
        if not clips:
            self.status.message("Nothing to run. Import a clip first." if not self.clips
                                else "Selected clips are already queued or running.")
            return
        bad = [c for c in preflight(REPO_ROOT, self.prefs.get("ffmpeg") or "ffmpeg")
               if not c.ok and not self.infer_script_override and "CK2_GUI_INFER" not in os.environ]
        if bad:
            QMessageBox.critical(
                self, "CorridorKey is not fully set up",
                "\n".join(f"\u2717 {b.name}: {b.detail}" for b in bad)
                + "\n\nFrom the repository root run:\n    python scripts/download_weights.py\n"
                  "and make sure ffmpeg is on your PATH.")
            return
        # one folder per clip, no collisions
        dirs: dict[str, str] = {}
        for c in self.clips:
            dirs.setdefault(os.path.normpath(self._out_dir(c)), c.id)
        existing = []
        plans = []
        for c in clips:
            herr = self._ensure_marker_hint(c)
            errs = [herr] if herr else validate(c)
            od = self._out_dir(c)
            owner = dirs.get(os.path.normpath(od))
            if owner and owner != c.id:
                errs.append(f"Output folder is shared with another clip: {od}")
            if errs:
                c.status, c.message = "ERROR", errs[0]
                continue
            if discover_outputs(od, c.name, prefer=c.settings.output_format) and not self._skip_overwrite_prompt:
                existing.append(c.name)
            plans.append((c, od))
        if existing:
            r = QMessageBox.question(
                self, "Overwrite outputs?",
                "Outputs already exist for:\n  " + "\n  ".join(existing[:8])
                + ("\n  ..." if len(existing) > 8 else "") + "\n\nOverwrite them?")
            if r != QMessageBox.Yes:
                self._refresh_all()
                return
        for c, od in plans:
            cmd = build_command(self.python, self.infer_script, c, od, self.prefs.get("ffmpeg", ""))
            _a, n = processed_range(c.frames, c.kind, c.settings)
            c.status, c.message = "QUEUED", ""
            c.ran_start, c.ran_dir = _a, od
            self.runner.enqueue(c.id, c.name, cmd, od, n, c.settings.low_vram)
        self._refresh_all()

    def stop(self) -> None:
        self._batch_stopped = True
        self.runner.cancel_all()

    # runner callbacks
    def _on_runner_changed(self) -> None:
        self.queue.refresh(self.runner.view())
        self.status.set_running(self.runner.is_busy())
        self._update_run_label()

    def _on_job_started(self, job) -> None:
        c = self.clip_by_id(job.clip_id)
        if c:
            c.status = "RUNNING"
            self._scan_outputs(c)
            if self.current is c:
                self.viewer.refresh_tabs()
                self.viewer.set_mode("input")
                self._update_scrubber()
        self.status.progress.set_fraction(0)
        self.status.message(f"{job.name}: starting...")
        self._refresh_tray()

    def _on_job_progress(self, job) -> None:
        p = job.parser
        self.status.progress.set_fraction(p.fraction)
        total = f"/{p.total}" if p.total else ""
        detail = f" frame {p.frame}{total}" if p.frame else ""
        extra = f"  [{p.auto_note}]" if p.auto_note and p.phase in ("LOADING MODEL", "ANALYSING", "KEYING") and not p.frame else ""
        self.status.message(f"{job.name}: {p.phase.lower()}{detail}{extra}")
        eta = job.eta_seconds()
        self.status.eta.setText(f"ETA {fmt_time(eta)}" if eta is not None else "")

    def _on_job_finished(self, job) -> None:
        c = self.clip_by_id(job.clip_id)
        self.status.eta.setText("")
        if c is None:
            return
        if job.status == "DONE":
            c.status = "COMPLETE"
            c.message = ""
            self._batch_done += 1
            self.status.message(f"Inference complete: {c.name}")
            self.status.progress.set_fraction(1.0)
        elif job.status == "CANCELLED":
            self._batch_stopped = True
            c.status = "CANCELLED"
            self.status.message(f"Cancelled: {c.name}")
        else:
            c.status, c.message = "ERROR", job.error
            self.status.message(f"Failed: {c.name}: {job.error}  (F12 for the full log)")
        if self.current is c and self.media is not None:
            self._scan_outputs(c)
            self.viewer.refresh_tabs()
            if self.media.has_outputs():
                pref = next((m for m in ("checker", "alpha", "fg", "cutout") if self.media.available(m)), "input")
                self.viewer.set_mode(pref)
            self.viewer.set_info(self._info(c), self._short_info(c))
            self._update_scrubber()
        self._refresh_tray()

    def _on_all_done(self) -> None:
        self.status.set_running(False)
        self.save()
        if self._batch_done and not self._batch_stopped:
            self.play_done_sound()
        self._batch_done, self._batch_stopped = 0, False

    def play_done_sound(self, force: bool = False) -> bool:
        """The "all done" chime. `force` plays it even if the option is off (used by the Test button)."""
        p = self.prefs
        if not (force or p.get("sound_on", True)):
            return False
        ok = self.sound.play(p.get("sound_chime", SND.DEFAULT_CHIME), p.get("sound_custom", ""),
                             bool(p.get("sound_use_custom")), int(p.get("sound_volume", 80)) / 100.0,
                             p.get("ffmpeg", ""))
        if not ok and self.sound.last_message:
            self.status.message("Sound: " + self.sound.last_message)
        return ok

    def _on_log_line(self, job_id: str, line: str) -> None:
        self.console_text.appendPlainText(line)

    # --------------------------------------------------------- subject marker
    # Left-click the subject (keep) / right-click something to drop. The clicks become a rough
    # black-and-white matte (subject.py) that is written as a first-frame hint PNG, which is exactly
    # what `infer.py --hint_first_frame` takes. It is only valid for the FIRST frame that will be
    # processed, so markers are tied to that frame.
    def _marker_first_frame(self, c: Clip) -> int:
        return processed_range(c.frames, c.kind, c.settings)[0]

    def _hint_png_path(self, c: Clip) -> str:
        return str(config_dir() / "hints" / f"{c.id}.png")

    def _marker_active(self) -> bool:
        return self.current is not None and self.current.settings.hint_mode == "marker"

    def _marker_load(self, c: Clip) -> None:
        """Called whenever a clip becomes current: rebuild the tint from the saved hint image."""
        self._marker_overlay = None
        s = c.settings
        if s.hint_mode == "marker" and s.hint_path and os.path.exists(s.hint_path):
            try:
                matte = subject.read_gray(s.hint_path)
                if matte is not None:
                    self._marker_overlay = subject.make_overlay(matte)
            except Exception:
                self._marker_overlay = None
        self._marker_sig = (s.hint_mode, s.marker_grow, s.marker_soft)
        self.params.set_marker_mode(False)
        self.viewer.set_marker_mode(False)
        self._marker_view_sync()
        self._marker_status()

    def _marker_view_sync(self) -> None:
        c = self.current
        show = (c is not None and c.settings.hint_mode == "marker"
                and self.viewer.frame_idx == c.settings.marker_frame)
        self.viewer.set_markers(c.settings.markers if show else [])
        self.viewer.set_overlay(self._marker_overlay if show else None)

    def _marker_status(self, extra: str = "", ok: bool = True) -> None:
        c = self.current
        if c is None:
            return
        s = c.settings
        a = self._marker_first_frame(c)
        keep = sum(1 for m in s.markers if m[2] > 0)
        drop = len(s.markers) - keep
        if not s.markers:
            self.params.set_marker_status("No markers yet. Press the button above, then left-click the subject.", True)
            return
        if s.marker_frame != a:
            self.params.set_marker_status(
                f"Your markers are on frame {s.marker_frame + 1}, but processing now starts at frame {a + 1}. "
                "Press GO TO FRAME and place them again.", False)
            return
        if not keep:
            self.params.set_marker_status("Only 'remove' markers so far - left-click the subject to keep it.", False)
            return
        txt = f"{keep} keep, {drop} remove \u00b7 frame {a + 1}"
        if extra:
            txt += " \u00b7 " + extra
        self.params.set_marker_status(txt, ok)

    def _on_marker_mode(self, on: bool) -> None:
        c = self.current
        self.viewer.set_marker_mode(bool(on and c is not None and c.settings.hint_mode == "marker"))
        if on and c is not None:
            self.viewer.set_mode("input")
            self._marker_goto()
            self.status.message("Marker mode: left-click the subject to keep it, right-click anything you want "
                                "removed. Dragging still pans.")

    def _marker_goto(self) -> None:
        if self.current is not None and self.media is not None:
            self.scrub.go(self._marker_first_frame(self.current))
            self._marker_view_sync()

    def _on_marker_click(self, nx: float, ny: float, sign: int) -> None:
        c = self.current
        if c is None or self.media is None or c.settings.hint_mode != "marker":
            return
        a = self._marker_first_frame(c)
        if self.viewer.frame_idx != a:
            self._marker_goto()
            self.status.message(f"Markers belong on the first frame that will be processed (frame {a + 1}). "
                                "Jumped there - click the subject again.")
            return
        s = c.settings
        if s.marker_frame != a:
            s.markers = []                  # markers from some other frame no longer describe this one
        s.marker_frame = a
        s.markers.append([round(float(nx), 4), round(float(ny), 4), 1 if sign > 0 else -1])
        self._marker_view_sync()
        self._marker_status("working...")
        self._marker_timer.start()

    def _marker_undo(self) -> None:
        if self._marker_active() and self.current.settings.markers:
            self.current.settings.markers.pop()
            self._marker_view_sync()
            self._marker_timer.start()

    def _marker_clear(self) -> None:
        if self._marker_active():
            self.current.settings.markers = []
            self._marker_view_sync()
            self._marker_timer.start()

    def _marker_params_changed(self) -> None:
        """Mode switch / grow / softness / frame-range edits in the parameter panel."""
        c = self.current
        if c is None:
            return
        s = c.settings
        sig = (s.hint_mode, s.marker_grow, s.marker_soft)
        old, self._marker_sig = self._marker_sig, sig
        if sig[0] == "marker" and old and old[0] != "marker" and not s.markers and s.hint_path:
            s.hint_path = ""                # a hint file from another mode is not a marker hint
            self._sig = self._signature(c)
            self._marker_overlay = None
            self.media.reload_hint()
            self.viewer.refresh_tabs()
        if sig[0] != "marker":
            self.viewer.set_marker_mode(False)
            if old and old[0] == "marker":
                self._marker_view_sync()
            return
        if old != sig and any(m[2] > 0 for m in s.markers) and s.marker_frame == self._marker_first_frame(c):
            self._marker_timer.start()      # (re)build the hint after a mode switch or a grow / softness change
        self._marker_view_sync()
        self._marker_status()

    def _build_marker_hint(self, c: Clip, rgb) -> tuple[Optional[str], Optional[object], str]:
        """-> (hint png path | None, matte | None, message)."""
        s = c.settings
        try:
            res = subject.segment_subject(rgb, s.markers, s.marker_grow / 10.0, s.marker_soft / 10.0)
            path = self._hint_png_path(c)
            subject.write_hint_png(path, res.matte)
        except Exception as e:
            return None, None, f"Could not build the subject hint: {e}"
        pct = res.coverage * 100.0
        if res.coverage <= 0.0:
            return None, None, "nothing is selected - left-click the subject"
        note = f"subject = {pct:.0f}% of the frame"
        if pct < 0.5:
            note += " (tiny - add 'keep' clicks on more parts of the subject)"
        elif pct > 85:
            note += " (almost everything - right-click the parts you do not want)"
        return path, res.matte, note

    def _marker_regenerate(self) -> None:
        c = self.current
        if c is None or self.media is None or c.settings.hint_mode != "marker":
            return
        s = c.settings
        a = self._marker_first_frame(c)
        if not any(m[2] > 0 for m in s.markers):
            s.hint_path = ""
            self._marker_overlay = None
        elif s.marker_frame != a:
            self._marker_status()
            return
        else:
            rgb, _note = self.media.frame("input", a)
            if rgb is None:
                self._marker_status("could not read the frame", False)
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                path, matte, note = self._build_marker_hint(c, rgb)
            finally:
                QApplication.restoreOverrideCursor()
            if path is None:
                s.hint_path = ""
                self._marker_overlay = None
                self.media.reload_hint()
                self.viewer.refresh_tabs()
                self._marker_view_sync()
                self._marker_status(note, False)
                return
            s.hint_path = path
            self._marker_overlay = subject.make_overlay(matte)
            self._sig = self._signature(c)
            self._marker_status(note, "tiny" not in note and "almost" not in note)
        self.media.reload_hint()
        self.viewer.refresh_tabs()
        self._marker_view_sync()
        self._update_scrubber()
        self.save()

    def _ensure_marker_hint(self, c: Clip) -> str:
        """Right before a run: rebuild the marker hint from the stored clicks so it always matches them."""
        s = c.settings
        if s.hint_mode != "marker" or not any(m[2] > 0 for m in s.markers):
            return ""                       # validate() reports a missing marker
        a = self._marker_first_frame(c)
        if s.marker_frame != a:
            return ""                       # validate() explains the frame mismatch
        if self.current is c and self.media is not None:
            rgb, _n = self.media.frame("input", a)
        else:
            rgb = None
            try:
                src = sources.open_source(c.path, linear=s.frame_linear, fps=s.frame_fps)
                fr = src.frame(a)
                src.close()
                rgb = fr[0] if fr else None
            except Exception:
                rgb = None
        if rgb is None:
            return f"{c.name}: could not read frame {a + 1} to build the subject hint."
        path, _m, note = self._build_marker_hint(c, rgb)
        if path is None:
            return f"{c.name}: {note}"
        s.hint_path = path
        return ""

    # ------------------------------------------------------ send to Nuke / AE
    def export_to(self, kind: str, quiet: bool = False) -> str:
        label = exports.KINDS[kind][0]
        c = self.current
        if c is None:
            self.status.message("Select a clip first.")
            return ""
        try:
            path = exports.write_export(kind, c, self._out_dir(c))
        except ValueError as e:
            if not quiet:
                QMessageBox.information(self, f"Send to {label}", str(e))
            self.status.message(str(e))
            return ""
        except OSError as e:
            if not quiet:
                QMessageBox.warning(self, f"Send to {label}", f"Could not write the script: {e}")
            return ""
        self.status.message(f"Wrote {path}")
        if not quiet:
            how = ("In Nuke: File > Open, or File > Insert Comp Nodes to paste the Read nodes into your own "
                   "script. Connect CK_Premult to the A input of a Merge on your background."
                   if kind == "nuke" else
                   "In After Effects: File > Scripts > Run Script File... and pick this file. It imports "
                   "the results into a folder and builds a comp.")
            box = QMessageBox(self)
            box.setWindowTitle(f"Send to {label}")
            box.setText(f"Saved next to your results:\n{path}\n\n{how}")
            open_btn = box.addButton("Show in folder", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Close)
            box.exec()
            if box.clickedButton() is open_btn:
                self._open_folder(os.path.dirname(path))
        return path

    # ---------------------------------------------------------------- tray etc
    def _card_menu(self, cid: str, pos) -> None:
        c = self.clip_by_id(cid)
        if c is None:
            return
        m = QMenu(self)
        m.addAction("Run inference", lambda: self.run_clips([c]))
        m.addAction("Set output folder...", lambda: self._set_out_dir(c))
        m.addAction("Open output folder", lambda: self._reveal_outputs_for(cid))
        m.addAction("Reveal source", lambda: self._reveal(c.path))
        m.addSeparator()
        m.addAction("Remove", lambda: (self.select_clip(cid), self.remove_selected()))
        m.exec(pos)

    def _set_out_dir(self, c: Clip) -> None:
        p = QFileDialog.getExistingDirectory(self, "Output folder for " + c.name, self._out_dir(c))
        if p:
            c.settings.out_dir = p
            if self.current is c:
                self.params.set_settings(c.settings, c.kind)
                self._scan_outputs(c)
                self.viewer.refresh_tabs()
                self.viewer.refresh()

    def _reveal(self, path: str) -> None:
        p = Path(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))

    def _reveal_outputs_for(self, cid: str) -> None:
        c = self.clip_by_id(cid)
        if c is None:
            return
        d = self._out_dir(c)
        if os.path.isdir(d):
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))
        else:
            self.status.message("No output folder yet: run inference first.")

    def _refresh_tray(self) -> None:
        self.tray.refresh(self.clips, self.thumbs, set(self.selected))

    def _update_run_label(self) -> None:
        n = len(self.selected)
        self.status.set_run_label(f"RUN SELECTED ({n})" if n > 1 else "RUN INFERENCE")
        busy = self.runner.is_busy()
        self.status.run.setEnabled(busy or bool(self.clips))        # STOP stays clickable
        self.status.run_all.setEnabled(not busy and bool(self.clips))

    def _refresh_all(self) -> None:
        self._refresh_tray()
        self.queue.refresh(self.runner.view())
        if self.current is None:
            self.stack.setCurrentIndex(0)
            self.params.set_settings(None, "video")
            self.scrub.set_state(0, 0)
        elif self.media is not None:
            self.viewer.set_info(self._info(self.current), self._short_info(self.current))
        self._update_run_label()

    def _toggle_console(self) -> None:
        self.console.setVisible(not self.console.isVisible())

    # -------------------------------------------------------------- dialogs
    # ----------------------------------------------------------- settings / theme
    def _apply_prefs(self) -> None:
        """Push theme + hover-help preferences into the running application."""
        H.ENABLED = bool(self.prefs.get("help_on", True))
        name = self.prefs.get("theme", "dark")
        if name not in T.THEME_NAMES:
            name = "dark"
        custom = normalised_custom(self.prefs.get("custom_theme"))
        app = QApplication.instance()
        if app is not None:
            T.retheme(app, name, custom)
        else:
            T.set_theme(name, custom)
        if hasattr(self, "params"):
            self.params.refresh_help()

    def _preview_theme(self, name: str, custom: dict) -> None:
        app = QApplication.instance()
        if app is not None:
            T.retheme(app, name, normalised_custom(custom))

    def _open_folder(self, path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def make_settings_dialog(self) -> SettingsDialog:
        d = SettingsDialog(self, self.prefs, self.sound,
                           {"python": find_python(), "infer": str(REPO_ROOT / "infer.py")},
                           str(config_dir()), self._open_folder)
        d.themePreview.connect(self._preview_theme)
        return d

    def open_settings(self) -> None:
        d = self.make_settings_dialog()
        accepted = bool(d.exec())
        if accepted:
            self.prefs.update(d.values())
        self._apply_prefs()                 # accepted: keep the new look; cancelled: undo the live preview
        if accepted:
            self.save()
            if self.current and self.media:
                self._scan_outputs(self.current)
                self.viewer.refresh_tabs()
                self.viewer.refresh()

    preferences = open_settings

    def system_check(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("System check")
        d.resize(700, 340)
        l = QVBoxLayout(d)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setFont(T.mono_font(11))
        l.addWidget(txt)
        lines = [f"GUI {__version__}   repo: {REPO_ROOT}", f"python: {self.python}", ""]
        for c in preflight(REPO_ROOT, self.prefs.get("ffmpeg") or "ffmpeg"):
            lines.append(f"{'OK  ' if c.ok else 'FAIL'}  {c.name}: {c.detail}")
        lines += ["", "checking torch / CUDA in that python..."]
        txt.setPlainText("\n".join(lines))
        proc = QProcess(d)

        def done(*_):
            out = bytes(proc.readAllStandardOutput()).decode(errors="replace").strip()
            txt.appendPlainText(out or "no output (is torch installed in that python?)")
        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda *_: txt.appendPlainText("could not start python"))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.start(self.python, ["-c", "import torch;print('torch', torch.__version__, "
                                       "'| CUDA available:', torch.cuda.is_available())"])
        row = QHBoxLayout()
        note = QLabel("")
        note.setWordWrap(True)
        cp = QPushButton("COPY FOR A BUG REPORT")
        cp.setObjectName("ghost")
        cp.setToolTip("Copies this text with your Windows/Linux account name taken out of every folder path, "
                      "so it is safe to paste into a public GitHub issue. Skim it before you paste.")
        cp.clicked.connect(lambda: note.setText(self.copy_scrubbed(txt.toPlainText())))
        row.addWidget(cp)
        row.addWidget(note, 1)
        l.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject)
        bb.clicked.connect(d.reject)
        l.addWidget(bb)
        d.exec()

    def copy_scrubbed(self, text: str) -> str:
        """Put `text` on the clipboard with the account name removed from paths. Returns a message for the user."""
        clean = scrub(text)
        QApplication.clipboard().setText(clean)
        return ("Copied. Your user name was replaced by <user> in folder paths. File names are untouched - "
                "skim before pasting." if clean != text else "Copied. (No user folder names were found in this text.)")

    def show_shortcuts(self) -> None:
        QMessageBox.information(self, "Keyboard shortcuts", (
            "Ctrl+O  import clips          Ctrl+S  save session\n"
            "Ctrl+R  run selected          Ctrl+Shift+R  run all ready\n"
            "Esc     stop                  Del  remove selected clips\n"
            "Ctrl+,  settings (theme, sound, paths)\n"
            "Q       toggle queue          F12  console\n"
            "F1-F6   INPUT / HINT / FG / MATTE / COMP / PROC\n"
            "A       A/B wipe              Ctrl+0  reset zoom\n"
            "Space   play / pause          \u2190 \u2192  step frame   Home / End  first / last\n"
            "Wheel   zoom at cursor        Drag / middle-drag  pan      Double-click  reset\n"
            "Shift+wheel  pan sideways     Middle-click a slider  reset to default\n"
            "Subject Marker: left-click = keep, right-click = remove (drag still pans)"))

    def about_html(self) -> str:
        """The About text. The author name is the only link; everything else is plain text."""
        link = (f'<a href="{AUTHOR_URL}" style="color:{T.c("ACCENT_FG")};">{escape(AUTHOR_NAME)}</a>')
        return (
            f"<p style='margin:0 0 6px 0'><b>{escape(APP_NAME)}</b> &nbsp;(GUI {escape(__version__)})</p>"
            f"<p style='margin:0 0 8px 0'>Vibecoded by {link} using {escape(CREDIT_MODEL)}</p>"
            "<p style='margin:0 0 8px 0'>An unofficial front-end for the CorridorKey 2.0 runtime by Corridor Digital. "
            "It is not affiliated with or endorsed by Corridor Digital.</p>"
            "<p style='margin:0 0 8px 0'>It runs the official <code>infer.py</code> as a separate process and does not "
            "change the model or its output. The Subject Marker only builds a first-frame hint image for the model; "
            "Send-to-Nuke / After Effects write small import scripts next to your results.</p>"
            "<p style='margin:0 0 8px 0'><b>Privacy:</b> no accounts, no telemetry, no update checks. The window itself makes "
            "no network connections; settings stay in a folder on this computer. The only thing that opens "
            "a web page is clicking the author's name, and that opens your own browser.</p>"
            "<p style='margin:0'>CorridorKey is free to use, including commercially, but may not be sold or offered as "
            "a paid service, and anything you release built on it must stay free, keep the CorridorKey name and carry "
            "the same license (see LICENSE). Organizations above US$20M annual revenue need the plugin seat from "
            "corridorkey.com.</p>")

    def open_author_link(self, url: str) -> None:
        """Only the one known address is ever opened from the About box."""
        if url == AUTHOR_URL:
            QDesktopServices.openUrl(QUrl(url))

    def about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("About")
        box.setIcon(QMessageBox.Information)
        box.setTextFormat(Qt.RichText)
        box.setText(self.about_html())
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        lab = box.findChild(QLabel, "qt_msgbox_label")
        if lab is not None:
            lab.setOpenExternalLinks(False)
            lab.setWordWrap(True)
            lab.setMinimumWidth(460)
            lab.linkActivated.connect(self.open_author_link)
            lab.setToolTip("")
        self._about_box = box
        box.exec()

    # ------------------------------------------------------------- lifecycle
    def save(self) -> None:
        try:
            save_session(self.clips, self.prefs)
        except OSError:
            pass

    def closeEvent(self, e):
        if self.runner.is_busy():
            r = QMessageBox.question(self, "Quit", "A job is still running. Stop it and quit?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.runner.cancel_all()
            if self.runner._proc is not None:
                self.runner._proc.waitForFinished(5000)
        self.save()
        self._close_media()
        super().closeEvent(e)
