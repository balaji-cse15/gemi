"""Background task runner — concurrent jobs that don't block the REPL.

Use cases:
  - Long-running shell commands (e.g. building, testing) while user types
  - Multi-agent vote/race in the background
  - Periodic checks / file watchers

Each job has:
  - id (auto: bg_<n>)
  - title (description)
  - state: pending | running | done | failed | cancelled
  - started_at, ended_at, elapsed
  - output (stdout+stderr captured)
  - exit_code (for shell jobs)
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from . import logger as logger_mod

JobState = Literal["pending", "running", "done", "failed", "cancelled"]


@dataclass
class Job:
    id: str
    title: str
    kind: str = "shell"  # shell | function
    state: JobState = "pending"
    started_at: float = 0.0
    ended_at: float = 0.0
    output: str = ""
    exit_code: int | None = None
    error: str = ""
    process: subprocess.Popen | None = None
    thread: threading.Thread | None = None

    @property
    def elapsed(self) -> float:
        if self.ended_at:
            return self.ended_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return 0.0


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()
_COUNTER = [0]


def _next_id() -> str:
    with _LOCK:
        _COUNTER[0] += 1
        return f"bg{_COUNTER[0]}"


def list_jobs(include_done: bool = True) -> list[Job]:
    with _LOCK:
        jobs = list(_JOBS.values())
    if not include_done:
        jobs = [j for j in jobs if j.state in ("pending", "running")]
    return jobs


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def _run_shell(job: Job, command: str, cwd: str = "", timeout: int = 600) -> None:
    job.state = "running"
    job.started_at = time.time()
    logger_mod.log("bg.start", job_id=job.id, job_kind="shell", title=job.title)
    try:
        job.process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd or None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            output, _ = job.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            job.process.kill()
            output, _ = job.process.communicate()
            job.error = f"timed out after {timeout}s"
            job.state = "failed"
            job.output = (output or "")[-30000:]
            return
        job.output = (output or "")[-30000:]
        job.exit_code = job.process.returncode
        job.state = "done" if job.exit_code == 0 else "failed"
    except Exception as e:
        job.error = str(e)
        job.state = "failed"
    finally:
        job.ended_at = time.time()
        logger_mod.log(
            "bg.end", job_id=job.id, state=job.state,
            exit_code=job.exit_code, elapsed=job.elapsed,
        )


def _run_function(job: Job, fn: Callable[[], Any]) -> None:
    job.state = "running"
    job.started_at = time.time()
    logger_mod.log("bg.start", job_id=job.id, job_kind="function", title=job.title)
    try:
        result = fn()
        job.output = str(result)[-30000:] if result is not None else ""
        job.state = "done"
    except Exception as e:
        import traceback
        job.error = str(e)
        job.output = traceback.format_exc()[-3000:]
        job.state = "failed"
    finally:
        job.ended_at = time.time()
        logger_mod.log("bg.end", job_id=job.id, state=job.state, elapsed=job.elapsed)


def spawn_shell(command: str, title: str = "", cwd: str = "", timeout: int = 600) -> Job:
    job = Job(id=_next_id(), title=title or command[:60], kind="shell")
    with _LOCK:
        _JOBS[job.id] = job
    job.thread = threading.Thread(target=_run_shell, args=(job, command, cwd, timeout), daemon=True)
    job.thread.start()
    return job


def spawn_function(fn: Callable[[], Any], title: str = "fn") -> Job:
    job = Job(id=_next_id(), title=title, kind="function")
    with _LOCK:
        _JOBS[job.id] = job
    job.thread = threading.Thread(target=_run_function, args=(job, fn), daemon=True)
    job.thread.start()
    return job


def cancel(job_id: str) -> bool:
    job = _JOBS.get(job_id)
    if not job:
        return False
    if job.state not in ("pending", "running"):
        return False
    if job.process:
        try:
            job.process.terminate()
            try:
                job.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                job.process.kill()
            job.state = "cancelled"
            job.ended_at = time.time()
            logger_mod.log("bg.cancel", job_id=job.id)
            return True
        except Exception:
            return False
    return False


def clear_completed() -> int:
    """Remove all jobs in done/failed/cancelled state. Returns count cleared."""
    with _LOCK:
        to_drop = [
            jid for jid, j in _JOBS.items()
            if j.state in ("done", "failed", "cancelled")
        ]
        for jid in to_drop:
            del _JOBS[jid]
    return len(to_drop)


def get_recent_completion() -> Job | None:
    """Return the most recently completed job (or None). Useful for notifications."""
    with _LOCK:
        completed = [j for j in _JOBS.values() if j.ended_at]
    if not completed:
        return None
    return max(completed, key=lambda j: j.ended_at)
