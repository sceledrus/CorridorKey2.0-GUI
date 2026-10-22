"""Runs infer.py as a subprocess (one job at a time) and watches the GPU.

Why a subprocess: the model needs ~5 GB of weights and a CUDA context. Keeping
that in a child process means the GUI stays responsive, Stop really frees the
GPU, a CUDA out-of-memory crash cannot take the window down, and the results
are byte-for-byte what `python infer.py` produces.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .model import REPO_ROOT, ProgressParser, parse_nvidia_smi

_ids = itertools.count(1)


@dataclass
class Job:
    clip_id: str
    name: str
    cmd: list
    out_dir: str
    parser: ProgressParser
    title: str = "Inference"
    id: str = field(default_factory=lambda: f"job{next(_ids)}")
    status: str = "QUEUED"        # QUEUED RUNNING DONE ERROR CANCELLED
    started: float = 0.0
    finished: float = 0.0
    log: list = field(default_factory=list)
    error: str = ""

    def eta_seconds(self) -> Optional[float]:
        f = self.parser.fraction
        if self.status != "RUNNING" or f <= 0.02 or not self.started:
            return None
        elapsed = time.time() - self.started
        return elapsed / f * (1.0 - f)


class JobRunner(QObject):
    changed = Signal()
    jobStarted = Signal(object)
    jobProgress = Signal(object)
    jobFinished = Signal(object)
    logLine = Signal(str, str)
    allDone = Signal()

    def __init__(self, workdir=REPO_ROOT, parent=None):
        super().__init__(parent)
        self.workdir = str(workdir)
        self.jobs: list[Job] = []
        self.current: Optional[Job] = None
        self._proc: Optional[QProcess] = None
        self._buf = ""
        self._cancel_requested = False

    # -- queue -----------------------------------------------------------------
    def enqueue(self, clip_id: str, name: str, cmd: list, out_dir: str,
                total_frames: int, low_vram: bool) -> Job:
        job = Job(clip_id, name, cmd, out_dir, ProgressParser(total_frames, low_vram))
        self.jobs.append(job)
        self.changed.emit()
        if self.current is None:
            self._start_next()
        return job

    def is_busy(self) -> bool:
        return self.current is not None

    def queued_for(self, clip_id: str) -> bool:
        return any(j.clip_id == clip_id and j.status in ("QUEUED", "RUNNING") for j in self.jobs)

    def remove(self, job_id: str) -> None:
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None or job.status == "RUNNING":
            return
        self.jobs.remove(job)
        if job.status == "QUEUED":
            self.jobFinished.emit(self._as_cancelled(job))
        self.changed.emit()

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if j.status in ("QUEUED", "RUNNING")]
        self.changed.emit()

    def cancel_all(self) -> None:
        for j in [j for j in self.jobs if j.status == "QUEUED"]:
            j.status = "CANCELLED"
            self.jobFinished.emit(j)
        self.cancel_current()
        self.changed.emit()

    def cancel_current(self) -> None:
        if self._proc is None:
            return
        self._cancel_requested = True
        self._proc.terminate()
        QTimer.singleShot(4000, self._kill_if_alive)

    def _kill_if_alive(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.kill()

    @staticmethod
    def _as_cancelled(job: Job) -> Job:
        job.status = "CANCELLED"
        return job

    def view(self) -> list[dict]:
        return [{"id": j.id, "title": j.title, "name": j.name, "status": j.status}
                for j in self.jobs]

    # -- process ------------------------------------------------------------------
    def _start_next(self) -> None:
        if self.current is not None:      # a deferred call must never clobber a running job
            return
        job = next((j for j in self.jobs if j.status == "QUEUED"), None)
        if job is None:
            self.current = None
            self.changed.emit()
            self.allDone.emit()
            return
        self.current = job
        job.status = "RUNNING"
        job.started = time.time()
        self._buf = ""
        self._cancel_requested = False
        proc = QProcess(self)
        self._proc = proc
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HF_HUB_OFFLINE", "1")
        env.insert("TRANSFORMERS_OFFLINE", "1")
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(self.workdir)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._log(job, "$ " + " ".join(f'"{a}"' if " " in a else a for a in job.cmd))
        proc.start(job.cmd[0], job.cmd[1:])
        self.changed.emit()
        self.jobStarted.emit(job)

    def _log(self, job: Job, line: str) -> None:
        job.log.append(line)
        if len(job.log) > 5000:
            del job.log[:1000]
        self.logLine.emit(job.id, line)

    def _on_output(self) -> None:
        if self._proc is None or self.current is None:
            return
        job = self.current
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buf += data.replace("\r\n", "\n").replace("\r", "\n")
        *lines, self._buf = self._buf.split("\n")
        changed = False
        for line in lines:
            if not line.strip():
                continue
            self._log(job, line)
            changed |= job.parser.feed(line)
        if changed:
            self.jobProgress.emit(job)

    def _on_error(self, err) -> None:
        if err == QProcess.FailedToStart and self.current is not None:
            job = self.current
            job.error = f"Could not start: {job.cmd[0]}"
            self._log(job, job.error)
            self._finish(job, "ERROR")

    def _on_finished(self, code: int, _status) -> None:
        job = self.current
        if job is None:
            return
        if self._buf.strip():
            self._log(job, self._buf.strip())
            job.parser.feed(self._buf)
            self._buf = ""
        if self._cancel_requested:
            self._finish(job, "CANCELLED")
        elif code == 0:
            self._finish(job, "DONE")
        else:
            tail = [l for l in job.log[-12:] if l.strip() and not l.startswith("$")]
            job.error = next((l for l in reversed(tail) if "Error" in l or "error" in l),
                             tail[-1] if tail else f"exit code {code}")
            self._finish(job, "ERROR")

    def _finish(self, job: Job, status: str) -> None:
        if job.status not in ("RUNNING", "QUEUED"):
            return
        job.status = status
        job.finished = time.time()
        if status == "DONE":
            job.parser.fraction = 1.0
        proc, self._proc = self._proc, None
        if proc is not None:
            proc.deleteLater()
        self.current = None
        self.jobFinished.emit(job)
        self.changed.emit()
        QTimer.singleShot(0, self._start_next)


class GpuMonitor(QObject):
    updated = Signal(object)    # (name, used_GB, total_GB) | None

    def __init__(self, interval_ms: int = 2000, parent=None):
        super().__init__(parent)
        self._proc: Optional[QProcess] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._interval = interval_ms
        self._dead = False

    def start(self) -> None:
        self.poll()
        self._timer.start(self._interval)

    def poll(self) -> None:
        if self._dead or (self._proc is not None and self._proc.state() != QProcess.NotRunning):
            return
        p = QProcess(self)
        self._proc = p
        p.finished.connect(lambda *_: self._done(p))
        p.errorOccurred.connect(lambda *_: self._failed(p))
        p.start("nvidia-smi", ["--query-gpu=name,memory.used,memory.total",
                               "--format=csv,noheader,nounits"])

    def _done(self, p: QProcess) -> None:
        text = bytes(p.readAllStandardOutput()).decode("utf-8", errors="replace")
        info = parse_nvidia_smi(text)
        p.deleteLater()
        if p is self._proc:
            self._proc = None
        self.updated.emit(info)

    def _failed(self, p: QProcess) -> None:
        if p.error() == QProcess.FailedToStart:
            self._dead = True            # no nvidia-smi on this machine: stop polling
            self._timer.stop()
            self.updated.emit(None)
