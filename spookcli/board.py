"""
SpookCLI Board — The Haunted Bulletin Board System

A retro BBS-style TUI that surfaces local failure stats, recent haunt logs,
and a spooky message of the day, rendered entirely with ANSI escape codes and
click's echo/style API so it works on any terminal without extra dependencies.

Public API (called by cli.py and ghost.py):
    record_failure(stderr_text)   persist one failure event to ~/.spookcli_stats.json
    run_board()                   launch the interactive BBS session
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows so box-drawing characters don't crash on cp1252.
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

STATS_FILE = Path.home() / ".spookcli_stats.json"

# How many recent log entries to keep on disk (rolling window)
_MAX_LOG_ENTRIES = 50

# Error-type extractor: tries to pull the leading exception / tool name
_ERROR_CLASSIFIERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ModuleNotFoundError|No module named",   re.I), "ModuleNotFoundError"),
    (re.compile(r"ImportError",                           re.I), "ImportError"),
    (re.compile(r"SyntaxError|invalid syntax",            re.I), "SyntaxError"),
    (re.compile(r"IndentationError",                      re.I), "IndentationError"),
    (re.compile(r"PermissionError|Permission denied",     re.I), "PermissionError"),
    (re.compile(r"FileNotFoundError|No such file",        re.I), "FileNotFoundError"),
    (re.compile(r"TypeError",                             re.I), "TypeError"),
    (re.compile(r"ValueError",                            re.I), "ValueError"),
    (re.compile(r"KeyError",                              re.I), "KeyError"),
    (re.compile(r"AttributeError",                        re.I), "AttributeError"),
    (re.compile(r"IndexError",                            re.I), "IndexError"),
    (re.compile(r"RecursionError",                        re.I), "RecursionError"),
    (re.compile(r"ConnectionRefusedError|ECONNREFUSED",   re.I), "ConnectionRefusedError"),
    (re.compile(r"TimeoutError|timed out",                re.I), "TimeoutError"),
    (re.compile(r"git.*not found|fatal:.*git",            re.I), "git error"),
    (re.compile(r"npm ERR",                               re.I), "npm error"),
    (re.compile(r"docker",                                re.I), "docker error"),
    (re.compile(r"SSL|certificate",                       re.I), "SSL error"),
]


def _classify_error(stderr_text: str) -> str:
    """Return a short error-type label for *stderr_text*."""
    for pattern, label in _ERROR_CLASSIFIERS:
        if pattern.search(stderr_text):
            return label
    return "unknown error"


def _load_stats() -> dict[str, Any]:
    """Load stats from disk, returning a default structure on first run."""
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"total_failures": 0, "error_counts": {}, "log": []}


def _save_stats(stats: dict[str, Any]) -> None:
    """Persist stats to disk. Silently swallows write errors."""
    try:
        STATS_FILE.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def record_failure(stderr_text: str) -> None:
    """
    Record one failure event. Called by ghost.py on every trigger.

    Increments the total failure counter, buckets the error type,
    and appends a timestamped log entry (capped at _MAX_LOG_ENTRIES).
    """
    stats = _load_stats()
    error_type = _classify_error(stderr_text)

    stats["total_failures"] = stats.get("total_failures", 0) + 1
    counts: dict[str, int] = stats.setdefault("error_counts", {})
    counts[error_type] = counts.get(error_type, 0) + 1

    # Log entry: ISO timestamp + first non-blank line of stderr as snippet
    snippet = next(
        (ln.strip() for ln in stderr_text.splitlines() if ln.strip()),
        "(no stderr)"
    )[:80]
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": error_type,
        "snippet": snippet,
    }
    log: list[dict[str, Any]] = stats.setdefault("log", [])
    log.append(entry)
    stats["log"] = log[-_MAX_LOG_ENTRIES:]  # rolling window

    _save_stats(stats)


# ---------------------------------------------------------------------------
# Content data
# ---------------------------------------------------------------------------

_MOTD_QUOTES: list[str] = [
    "The stack trace is not the bug — it is merely the ghost of the bug.",
    "In this crypt, all merge conflicts are permanent.",
    "Your tests passed locally. They always do. The CI server knows the truth.",
    "pip install hope  -- ERROR: No matching distribution found.",
    "There are only two hard problems: cache invalidation, naming, and off-by-one.",
    "The best code is code that has never been written. The worst is yours.",
    "A senior dev has seen this error before. They still can't fix it.",
    "git blame never lies. That is why we fear it.",
    "Technical debt: the mortgage your ghost will pay long after you are gone.",
    "Every 'temporary fix' is just a haunting waiting to happen.",
    "The bug does not exist in production. It only exists when the client watches.",
    "You cannot refactor the dead. You can only inherit from them.",
    "undefined is not a function — and neither are you at 3 AM.",
    "The compiler does not care about your feelings. Neither do the tests.",
    "Dark mode does not protect you from what lurks in the logs.",
    "This server has been running since 2009. Do not touch it.",
    "README.md: last updated Halloween 2019. The project has changed.",
    "We do not delete legacy code. We bury it and pray.",
]

_ASCII_GHOST = r"""
     .-.
    (o o)
    | O |   S P O O K C L I
   /|---|\ 
  (_|   |_)
"""

_ASCII_PUMPKIN = r"""
    .-'-.
   /|6 6|\
  | | ^ | |  H A U N T E D
   \| v |/   B B S  v1.0
    `---'
"""

# Kiro Ghost sprite — rendered in Ethereal Cyan above the Haunt Log.
# Each string is exactly the visual line; leading spaces are intentional.
_KIRO_SPRITE_LINES: list[str] = [
    r"   .---.   ",
    r"  / \u25c9 \u25c9 \  ",
    r"  |  \u2316  |  ",
    r"  \~^~^~/  ",
]

# Pre-rendered with the Unicode escapes resolved (Python reads \uXXXX in source)
_KIRO_SPRITE_LINES = [
    "   .---.   ",
    "  / \u25c9 \u25c9 \\  ",
    "  |  \u2316  |  ",
    "  \\~^~^~/  ",
]

# Dissolve animation frames (3 frames, each a list of 4 lines matching sprite height)
_DISSOLVE_FRAMES: list[list[str]] = [
    [                         # Frame 1 — intact (same as sprite)
        "   .---.   ",
        "  / \u25c9 \u25c9 \\  ",
        "  |  \u2316  |  ",
        "  \\~^~^~/  ",
    ],
    [                         # Frame 2 — partial scatter
        "   .   .   ",
        "  . * * .  ",
        "  +  \u2316  +  ",
        "  . + . +  ",
    ],
    [                         # Frame 3 — dispersed
        "  .     .  ",
        "      .    ",
        "  .     .  ",
        "     .     ",
    ],
]

# ---------------------------------------------------------------------------
# ANSI / terminal helpers
# ---------------------------------------------------------------------------

# We keep our own thin ANSI wrappers so the renderer is readable and
# independent of any third-party TUI library.

def _ansi(code: str) -> str:
    return f"\x1b[{code}m"


# Legacy colour shortcuts (used by existing box/section renderers — DO NOT REMOVE)
_RESET   = _ansi("0")
_BOLD    = _ansi("1")
_DIM     = _ansi("2")
_GREEN   = _ansi("32")
_YELLOW  = _ansi("33")
_CYAN    = _ansi("36")
_WHITE   = _ansi("37")
_RED     = _ansi("31")
_MAGENTA = _ansi("35")
_BG_BLACK = _ansi("40")

# ── Magitech palette (256-colour) ──────────────────────────────────────────
# Muted Slate Gray  (ANSI 239) — borders and structural chrome
_MT_BORDER   = _ansi("38;5;239")
# Soft Off-White    (ANSI 254) — body text
_MT_TEXT     = _ansi("38;5;254")
# Ethereal Cyan     (ANSI 51)  — Kiro sprite, resurrection prompts, highlights
_MT_CYAN     = _ansi("38;5;51")
# Neon Green        (ANSI 118) — success flash
_MT_SUCCESS  = _ansi("38;5;118")
# Neon Red          (ANSI 196) — failure flash
_MT_FAIL     = _ansi("38;5;196")

# Double-line box-drawing characters (cp437 / UTF-8)
_TL = "\u2554"   # ╔
_TR = "\u2557"   # ╗
_BL = "\u255a"   # ╚
_BR = "\u255d"   # ╝
_H  = "\u2550"   # ═
_V  = "\u2551"   # ║
_ML = "\u2560"   # ╠
_MR = "\u2563"   # ╣

# Single-line divider (also used by cemetery histogram)
_SH = "\u2500"   # ─


def _width() -> int:
    """Terminal width, clamped to [60, 100]."""
    try:
        import shutil
        return max(60, min(100, shutil.get_terminal_size().columns))
    except Exception:
        return 80


def _box_top(w: int, colour: str = _CYAN) -> str:
    return f"{colour}{_BOLD}{_TL}{_H * (w - 2)}{_TR}{_RESET}"


def _box_bot(w: int, colour: str = _CYAN) -> str:
    return f"{colour}{_BOLD}{_BL}{_H * (w - 2)}{_BR}{_RESET}"


def _box_div(w: int, colour: str = _CYAN) -> str:
    return f"{colour}{_BOLD}{_ML}{_H * (w - 2)}{_MR}{_RESET}"


def _box_row(content: str, w: int, colour: str = _CYAN) -> str:
    """Pad *content* (plain text, no ANSI) to exactly w-2 chars inside pipes."""
    # Strip existing ANSI for length calculation only
    plain = re.sub(r"\x1b\[[0-9;]*m", "", content)
    pad = w - 2 - len(plain)
    return f"{colour}{_BOLD}{_V}{_RESET}{content}{' ' * max(pad, 0)}{colour}{_BOLD}{_V}{_RESET}"


def _centred(text: str, w: int, colour: str = "") -> str:
    """Return *text* centre-aligned in *w-2* columns with optional colour."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    total_pad = w - 2 - len(plain)
    left = total_pad // 2
    return _box_row(f"{' ' * left}{colour}{text}{_RESET}", w)


def _print(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Dial-up connection sequence
# ---------------------------------------------------------------------------

_CONNECT_LINES: list[tuple[str, float]] = [
    ("ATDT 1-900-HAUNTED",             0.25),
    ("",                               0.05),
    ("CONNECT 14400",                  0.30),
    ("PROTOCOL: V.42bis / MNP5",       0.20),
    ("",                               0.05),
    ("Authenticating spirit.........", 0.50),
    ("Access granted. Welcome, soul.", 0.25),
    ("",                               0.10),
    ("Loading haunted board...",       0.40),
    ("",                               0.15),
]

_MODEM_CHARS = "~!@#$%^*()[]<>{}|\\/?.,;:"


def _type_line(text: str, delay_per_char: float = 0.025) -> None:
    """Print *text* one character at a time, then newline."""
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay_per_char)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _modem_noise(duration: float = 0.6) -> None:
    """Print random modem-noise characters for *duration* seconds."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        ch = random.choice(_MODEM_CHARS)
        sys.stdout.write(f"{_GREEN}{ch}{_RESET}")
        sys.stdout.flush()
        time.sleep(0.02)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _play_board_audio() -> None:
    """Play the scream WAV as a modem-ish startup cue if audio is available."""
    try:
        from spookcli.ghost import _ensure_audio, _play_sound, _SCREAM_WAV
        if _ensure_audio():
            _play_sound(_SCREAM_WAV)
    except Exception:
        pass


def run_dial_sequence() -> None:
    """Render the animated dial-up connection preamble."""
    _print(f"\n{_GREEN}{_BOLD}", )
    _modem_noise(0.5)

    for line, pause in _CONNECT_LINES:
        if line:
            _type_line(f"{_GREEN}{_BOLD}{line}{_RESET}", delay_per_char=0.022)
        else:
            _print()
        time.sleep(pause)


# ---------------------------------------------------------------------------
# BBS board sections
# ---------------------------------------------------------------------------

def _render_banner(w: int) -> None:
    """ASCII art header."""
    lines = [ln for ln in _ASCII_GHOST.splitlines() if ln.strip()]
    _print(_box_top(w, _MAGENTA))
    for ln in lines:
        _print(_centred(f"{_YELLOW}{_BOLD}{ln}{_RESET}", w, colour=""))
    _print(_box_bot(w, _MAGENTA))


def _render_cemetery(stats: dict[str, Any], w: int) -> None:
    """Developer Cemetery — failure stats."""
    total: int = stats.get("total_failures", 0)
    counts: dict[str, int] = stats.get("error_counts", {})

    _print(_box_top(w, _RED))
    _print(_centred(f"{_RED}{_BOLD}*** THE DEVELOPER CEMETERY ***{_RESET}", w))
    _print(_centred(f"{_DIM}Inscribed in stone. Updated in real-time.{_RESET}", w))
    _print(_box_div(w, _RED))

    total_str = f"  Total curses recorded : {_YELLOW}{_BOLD}{total}{_RESET}"
    _print(_box_row(total_str, w, _RED))
    _print(_box_row("", w, _RED))

    if counts:
        _print(_box_row(f"  {_WHITE}{_BOLD}Cause of death          Count{_RESET}", w, _RED))
        _print(_box_row(f"  {_DIM}{_SH * (w - 6)}{_RESET}", w, _RED))
        for error_type, cnt in sorted(counts.items(), key=lambda x: -x[1])[:8]:
            bar_len   = min(20, cnt)
            bar       = f"{_RED}{'|' * bar_len}{_RESET}"
            label     = f"  {_CYAN}{error_type:<28}{_RESET} {_YELLOW}{cnt:>4}{_RESET}  {bar}"
            _print(_box_row(label, w, _RED))
    else:
        _print(_centred(f"{_DIM}No casualties yet. Your luck won't hold.{_RESET}", w))

    _print(_box_bot(w, _RED))


def _render_haunt_log(stats: dict[str, Any], w: int) -> list[dict[str, Any]]:
    """
    Latest Haunt Logs — most recent failures, indexed [1]–[7].

    Returns the list of displayed entries (newest-first) so the caller
    can map user index choices back to log positions.
    """
    log: list[dict[str, Any]] = stats.get("log", [])

    _print(_box_top(w, _YELLOW))
    _print(_centred(f"{_YELLOW}{_BOLD}*** LATEST HAUNT LOGS ***{_RESET}", w))
    _print(_centred(f"{_DIM}Recent screams intercepted from your shell.{_RESET}", w))
    _print(_box_div(w, _YELLOW))

    entries = list(reversed(log[-7:]))  # newest first, max 7
    if not entries:
        _print(_centred(f"{_DIM}The graveyard is empty. For now.{_RESET}", w))
    else:
        for idx, entry in enumerate(entries, start=1):
            ts_raw = entry.get("ts", "")
            try:
                dt = datetime.fromisoformat(ts_raw)
                ts_str = dt.strftime("%m-%d %H:%M")
            except ValueError:
                ts_str = ts_raw[:16]
            err_t   = entry.get("type", "?")[:18]
            # Reserve room for index tag + possible resurrected badge
            snippet = entry.get("snippet", "")[:w - 46]

            # Resurrected badge replaces snippet prefix when applicable
            status = entry.get("status", "")
            if status == "resurrected":
                badge = f"{_MT_SUCCESS}{_BOLD}(resurrected){_RESET} "
                snippet = badge + snippet
            else:
                snippet = f"{_MT_TEXT}{snippet}{_RESET}"

            index_tag = f"{_MT_CYAN}{_BOLD}[{idx}]{_RESET}"
            row = (
                f"  {index_tag} {_DIM}{ts_str}{_RESET}"
                f"  {_RED}{err_t:<18}{_RESET}"
                f"  {snippet}"
            )
            _print(_box_row(row, w, _YELLOW))

    _print(_box_bot(w, _YELLOW))
    return entries


def _render_motd(w: int) -> None:
    """Message of the Day — random spooky dev quote."""
    quote = random.choice(_MOTD_QUOTES)

    _print(_box_top(w, _CYAN))
    _print(_centred(f"{_CYAN}{_BOLD}*** MESSAGE OF THE DAY ***{_RESET}", w))
    _print(_box_div(w, _CYAN))

    # Word-wrap the quote to fit inside the box
    words  = quote.split()
    lines: list[str] = []
    current = ""
    inner_w = w - 6  # 2 borders + 2 spaces each side
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= inner_w:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    for ln in lines:
        _print(_box_row(f"  {_WHITE}{_BOLD}{ln}{_RESET}", w, _CYAN))

    _print(_box_row("", w, _CYAN))
    _print(_box_row(f"  {_DIM}-- The Phantom Sysop{_RESET}", w, _CYAN))
    _print(_box_bot(w, _CYAN))


# ---------------------------------------------------------------------------
# Kiro sprite renderer
# ---------------------------------------------------------------------------

def _render_kiro_sprite(w: int, lines: list[str] | None = None) -> None:
    """
    Render the Kiro Ghost sprite in Ethereal Cyan, centred in *w* columns.
    *lines* defaults to _KIRO_SPRITE_LINES; pass a dissolve frame to animate.
    """
    sprite = lines if lines is not None else _KIRO_SPRITE_LINES
    sprite_w = max(len(ln) for ln in sprite)
    pad = max(0, (w - sprite_w) // 2)
    for ln in sprite:
        _print(f"{' ' * pad}{_MT_CYAN}{_BOLD}{ln}{_RESET}")


# ---------------------------------------------------------------------------
# Resurrection helpers
# ---------------------------------------------------------------------------

def _render_resurrection_footer(w: int, entry_count: int) -> None:
    """
    Render the Resurrection control footer in the Magitech palette.

    Appended below all panels — never inside any box so existing alignments
    are not disturbed.
    """
    _print()
    if entry_count > 0:
        hint = (
            f"  {_MT_CYAN}{_BOLD}resurrect <1-{entry_count}>{_RESET}"
            f"{_MT_BORDER}  or just  {_RESET}"
            f"{_MT_CYAN}{_BOLD}<1-{entry_count}>{_RESET}"
            f"{_MT_BORDER}  to attempt resurrection{_RESET}"
        )
        _print(hint)
    disconnect = (
        f"  {_MT_BORDER}Q + Enter  disconnect"
        f"    Enter alone  refresh{_RESET}"
    )
    _print(disconnect)
    _print()


def _parse_resurrect_input(raw: str, max_idx: int) -> int | None:
    """
    Parse user input for a resurrection command.

    Accepts:
        "resurrect 3"  →  3
        "resurrect3"   →  3
        "3"            →  3
    Returns the 1-based index (int) or None if the input is not a valid command.
    """
    s = raw.strip().lower()
    # "resurrect N" or "resurrectN"
    m = re.match(r"^resurrect\s*(\d+)$", s)
    if m:
        idx = int(m.group(1))
        return idx if 1 <= idx <= max_idx else None
    # bare integer
    if re.match(r"^\d+$", s):
        idx = int(s)
        return idx if 1 <= idx <= max_idx else None
    return None


def _mark_resurrected(entry_ts: str) -> None:
    """
    Find the log entry matching *entry_ts* and set status = "resurrected".

    Writes back to STATS_FILE. Safe to call on a missing or corrupt file.
    """
    stats = _load_stats()
    for e in stats.get("log", []):
        if e.get("ts") == entry_ts:
            e["status"] = "resurrected"
            break
    _save_stats(stats)


def _play_resurrect_audio() -> None:
    """Play spookcli/assets/ghost_caught.wav if available, else fall back silently."""
    try:
        from spookcli.ghost import _ensure_audio, _play_sound, _ASSETS_DIR
        wav = _ASSETS_DIR / "ghost_caught.wav"
        if _ensure_audio():
            _play_sound(wav)   # _play_sound handles missing file gracefully
    except Exception:
        pass


def _dissolve_animation(w: int) -> None:
    """
    Play the 3-frame Kiro dissolve animation in-place below the panels.
    Each frame is rendered then overwritten using cursor-up escape sequences.
    """
    sprite_h = len(_DISSOLVE_FRAMES[0])

    for frame_idx, frame_lines in enumerate(_DISSOLVE_FRAMES):
        if frame_idx > 0:
            # Move cursor up sprite_h lines to overwrite previous frame
            sys.stdout.write(f"\x1b[{sprite_h}A")
            sys.stdout.flush()
        _render_kiro_sprite(w, lines=frame_lines)
        time.sleep(0.08)


# ---------------------------------------------------------------------------
# Main board renderer
# ---------------------------------------------------------------------------

def _render_board(
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Render all BBS panels: Banner, Cemetery, Kiro sprite, Haunt Log,
    MOTD, and the Resurrection footer.

    Returns the list of displayed haunt-log entries (newest-first, max 7)
    so the caller can map user index inputs back to log records.
    """
    w = _width()
    # ANSI clear-screen + cursor home
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()
    _render_banner(w)
    _print()
    _render_cemetery(stats, w)
    _print()
    _render_kiro_sprite(w)
    _print()
    entries = _render_haunt_log(stats, w)
    _print()
    _render_motd(w)
    _render_resurrection_footer(w, len(entries))
    return entries


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_board() -> None:
    """
    Launch the interactive Haunted BBS session.

    1. Plays audio cue and renders the animated dial-up sequence.
    2. Renders the full board on every loop iteration.
    3. Input loop:
       - Q / quit / exit / x  → disconnect and exit
       - Enter (blank)         → refresh
       - "resurrect N" / "N"  → resurrection flow for haunt-log entry N
    """
    import subprocess as _sp

    # ── audio cue ─────────────────────────────────────────────────────────
    _play_board_audio()

    # ── dial-up preamble ──────────────────────────────────────────────────
    run_dial_sequence()

    # ── interactive loop ──────────────────────────────────────────────────
    while True:
        stats   = _load_stats()
        entries = _render_board(stats)

        # ── read input ────────────────────────────────────────────────────
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            raw = "q"

        lower = raw.lower()

        # ── disconnect ────────────────────────────────────────────────────
        if lower in ("q", "quit", "exit", "x"):
            break

        # ── resurrection attempt ──────────────────────────────────────────
        res_idx = _parse_resurrect_input(raw, len(entries))
        if res_idx is not None:
            entry = entries[res_idx - 1]   # convert 1-based → 0-based
            failed_snippet = entry.get("snippet", "(unknown command)")

            # Magitech prompt — appended below current rendered output
            _print()
            prompt_line = (
                f"  {_MT_CYAN}{_BOLD}\u29e1 \u276f\u276f{_RESET}"
                f" {_MT_TEXT}Enter incantation (fix) for:{_RESET}"
                f" {_MT_CYAN}{failed_snippet}{_RESET}"
            )
            _print(prompt_line)
            sys.stdout.write(f"  {_MT_CYAN}{_BOLD}> {_RESET}")
            sys.stdout.flush()

            try:
                corrected = input().strip()
            except (EOFError, KeyboardInterrupt):
                corrected = ""

            if not corrected:
                continue   # blank input → refresh board

            # ── execute the corrected command ─────────────────────────────
            _print()
            _print(f"  {_MT_BORDER}Channelling the fix...{_RESET}")
            result = _sp.run(corrected, shell=True)

            w = _width()

            if result.returncode == 0:
                # Success: persist, play audio, dissolve animation, flash
                _mark_resurrected(entry.get("ts", ""))
                _play_resurrect_audio()

                _print()
                _dissolve_animation(w)

                success_msg = "[ COMMAND RESURRECTED ]"
                pad = max(0, (w - len(success_msg)) // 2)
                _print()
                _print(f"{' ' * pad}{_MT_SUCCESS}{_BOLD}{success_msg}{_RESET}")
                time.sleep(1.5)
            else:
                # Failure: red flash
                fail_msg = "[ RESURRECTION FAILED ]"
                pad = max(0, (w - len(fail_msg)) // 2)
                _print()
                _print(f"{' ' * pad}{_MT_FAIL}{_BOLD}{fail_msg}{_RESET}")
                time.sleep(1.5)

            continue   # re-render board

        # ── bare Enter or unrecognised input → refresh ────────────────────

    # ── disconnect message ────────────────────────────────────────────────
    _print()
    _type_line(f"{_GREEN}{_BOLD}NO CARRIER{_RESET}", delay_per_char=0.04)
    _print(f"{_DIM}Disconnected from the spirit realm. Goodbye.{_RESET}")
    _print()
