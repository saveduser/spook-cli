"""
spookcli/whispers.py — System Whispers: OS Anomaly Tracker

Polls the local OS every 15 seconds for "hauntings":
  • Restless Spirits  — zombie processes
  • Abandoned Timelines — git detached HEAD in cwd
  • Poltergeists      — top memory-consuming process

Architecture
────────────
A single daemon thread (started lazily on first call) owns all subprocess
and psutil calls. Results are written into a module-level list protected by
a threading.Lock. The ghost overlay calls get_current_whispers() which reads
that list without waiting — it always returns instantly.

Cross-platform rules (per steering/cross-platform-rules.md)
────────────────────────────────────────────────────────────
• Every subprocess call is wrapped in try/except and silently returns "" on
  any error — bash commands will not exist on Windows/WSL; that is fine.
• psutil is used for memory stats; if it raises (container, locked /proc,
  etc.) the poltergeist whisper is simply omitted.
• The background thread is daemon=True so it never blocks process exit.

Public API
──────────
  get_current_whispers() -> str
      Randomly picks and returns ONE whisper string from the current anomaly
      pool.  Returns the ambient fallback string if no anomalies are present.
      Always returns immediately — never blocks.

  start_whispers()
      Explicitly start the background poller.  Called by OverlayWindow.__init__.
      Calling it multiple times is a no-op.

  stop_whispers()
      Signal the background poller to stop.  Used in tests; not required for
      normal process exit because the thread is a daemon.
"""

from __future__ import annotations

import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Ambient fallback shown when no OS anomalies are detected
_AMBIENT_WHISPER = "The system is eerily quiet..."

# ── Polling interval (seconds) ─────────────────────────────────────────────
_POLL_INTERVAL: float = 15.0

# ── Module-level state (written only by the daemon thread) ─────────────────
_whispers_lock:   threading.Lock      = threading.Lock()
_current_whispers: list[str]          = []
_poller_thread:   threading.Thread | None = None
_stop_event:      threading.Event     = threading.Event()


# ───────────────────────────────────────────────────────────────────────────
# Individual OS probe functions
# Each returns a string (non-empty = anomaly found) or "" (clean / error).
# They MUST NOT raise — all exceptions are caught internally.
# ───────────────────────────────────────────────────────────────────────────

def _probe_zombies() -> list[str]:
    """
    Return one warning string per zombie PID found, or empty list.

    Uses psutil for cross-platform support; falls back to a POSIX `ps`
    command on Linux/macOS if psutil raises unexpectedly.
    """
    results: list[str] = []
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "status"]):
            try:
                if proc.info["status"] == psutil.STATUS_ZOMBIE:
                    pid = proc.info["pid"]
                    results.append(
                        f"[WARNING] Restless Spirit detected (Zombie PID: {pid})"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        # psutil unavailable or /proc unreadable — try POSIX fallback
        if sys.platform != "win32":
            try:
                out = subprocess.check_output(
                    ["ps", "aux"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
                for line in out.splitlines():
                    cols = line.split()
                    # column 7 (0-indexed) is the STAT field in BSD ps
                    if len(cols) > 7 and "Z" in cols[7]:
                        pid = cols[1]
                        results.append(
                            f"[WARNING] Restless Spirit detected (Zombie PID: {pid})"
                        )
            except Exception:
                pass
    return results


def _probe_detached_head() -> str:
    """
    Return an anomaly string if cwd is a git repo in detached HEAD state.

    Strategy: read .git/HEAD directly — avoids spawning git on non-repo
    directories and is instant.  Falls back to `git branch --show-current`
    if .git/HEAD is absent (worktrees, etc.).
    """
    try:
        cwd = Path.cwd()

        # Walk upward to find .git
        candidate = cwd
        git_head: Path | None = None
        for _ in range(8):  # don't walk above 8 levels
            head_file = candidate / ".git" / "HEAD"
            if head_file.exists():
                git_head = head_file
                break
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent

        if git_head is None:
            return ""  # not a git repo

        content = git_head.read_text(encoding="utf-8", errors="replace").strip()
        # Attached HEAD looks like: "ref: refs/heads/main"
        # Detached HEAD is a bare SHA: "a1b2c3d4..."
        if content.startswith("ref:"):
            return ""

        # Double-check with git command (catches worktree edge cases)
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
                cwd=str(cwd),
            ).strip()
            if branch:
                return ""  # on a named branch, not detached
        except Exception:
            pass  # git not available or timed out — trust HEAD file read

        return "[CHRONO-ANOMALY] You are haunting an Abandoned Timeline (Detached HEAD)"

    except Exception:
        return ""


def _probe_memory_hog() -> str:
    """
    Return an alert string naming the top memory-consuming process.

    Uses psutil for cross-platform accuracy.  Silently returns "" on any
    error (containers without /proc, permission restrictions, etc.).
    """
    try:
        import psutil  # type: ignore

        top_proc: Any = None
        top_mem: float = 0.0

        for proc in psutil.process_iter(["name", "memory_percent"]):
            try:
                mem = proc.info.get("memory_percent") or 0.0
                if mem > top_mem:
                    top_mem = mem
                    top_proc = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if top_proc is None or top_mem < 1.0:
            return ""  # nothing remarkable

        name = (top_proc.info.get("name") or "Unknown")[:24]
        return f"[ALERT] A Poltergeist is draining memory ({name} at {top_mem:.1f}%)"

    except Exception:
        return ""


# ───────────────────────────────────────────────────────────────────────────
# Background polling thread
# ───────────────────────────────────────────────────────────────────────────

def _poll_once() -> list[str]:
    """Collect all OS anomaly strings in a single poll cycle."""
    results: list[str] = []

    # Zombies — may return multiple entries
    results.extend(_probe_zombies())

    # Detached HEAD
    detached = _probe_detached_head()
    if detached:
        results.append(detached)

    # Memory hog
    hog = _probe_memory_hog()
    if hog:
        results.append(hog)

    return results


def _run_poller() -> None:
    """
    Daemon thread body.  Polls immediately, then every _POLL_INTERVAL seconds
    until _stop_event is set.
    """
    while not _stop_event.is_set():
        try:
            fresh = _poll_once()
        except Exception:
            fresh = []

        with _whispers_lock:
            _current_whispers.clear()
            _current_whispers.extend(fresh)

        # Sleep in small increments so _stop_event is checked promptly
        for _ in range(int(_POLL_INTERVAL / 0.5)):
            if _stop_event.is_set():
                break
            time.sleep(0.5)


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────

def start_whispers() -> None:
    """
    Start the background OS poller if it is not already running.

    Idempotent — safe to call multiple times.  The thread is a daemon so
    it will be cleaned up automatically when the process exits.
    """
    global _poller_thread

    if _poller_thread is not None and _poller_thread.is_alive():
        return  # already running

    _stop_event.clear()
    _poller_thread = threading.Thread(
        target=_run_poller,
        name="spookcli-whispers",
        daemon=True,
    )
    _poller_thread.start()


def stop_whispers() -> None:
    """
    Signal the background poller to stop cleanly.

    Returns immediately; the thread will exit within one poll interval.
    Intended for tests and clean teardown — normal process exit doesn't
    need this because the thread is a daemon.
    """
    _stop_event.set()


def get_current_whispers() -> str:
    """
    Pick and return ONE whisper string from the most recently polled anomalies.

    If the anomaly pool is empty (system is clean, or the first poll hasn't
    completed yet), returns the ambient fallback string.

    Always returns instantly — reads from an in-memory cache populated by
    the background daemon thread.
    """
    with _whispers_lock:
        pool = list(_current_whispers)

    if not pool:
        return _AMBIENT_WHISPER
    return random.choice(pool)
