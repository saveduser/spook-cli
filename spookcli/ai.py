"""
Spooky Error Intelligence — diagnoses terminal failures with ghost-flavoured wit.

Public API:
    get_spooky_diagnosis(stderr_text: str) -> str

Strategy (in order):
  1. POST to a local Ollama instance (http://localhost:11434/api/generate).
     Model preference: phi3, then llama3.  Timeout: 1.5 s.
  2. If Ollama is unreachable / times out / errors, fall back to a
     pattern-matching dictionary keyed on common error signatures.
  3. If nothing matches, return a generic spooky shrug.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import urllib.error
import urllib.request
from typing import Sequence

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

_OLLAMA_URL     = "http://localhost:11434/api/generate"
_OLLAMA_TIMEOUT = 1.5          # seconds — must feel instant to the user
_OLLAMA_MODELS  = ["phi3", "llama3"]  # tried in order until one responds

_SYSTEM_PROMPT = (
    "You are a mischievous, playful ghost haunting a developer's terminal. "
    "Given a command error or stack trace, give a 1-sentence witty, spooky "
    "explanation of what went wrong and how to fix it. "
    "Keep it under 120 characters. No markdown, no bullet points."
)


def _try_ollama(stderr_text: str) -> str | None:
    """
    Attempt to get a diagnosis from a local Ollama instance.

    Returns the model's response string on success, or None on any failure
    (connection refused, timeout, HTTP error, JSON parse error, …).

    Uses a daemon thread + join(timeout) instead of relying solely on the
    urllib socket timeout, because on Windows a TCP connect to a closed port
    can block for several seconds before the OS gives up — far longer than
    our 1.5 s budget.
    """
    # Fast pre-flight: can we even open a TCP socket to Ollama's port?
    # This avoids spawning threads when the service is clearly down.
    try:
        with socket.create_connection(("localhost", 11434), timeout=0.3):
            pass
    except OSError:
        return None  # port closed or unreachable — skip all model attempts

    truncated = stderr_text.strip()[-800:]

    def _call(model: str, bucket: list[str | None]) -> None:
        payload = json.dumps({
            "model":  model,
            "prompt": truncated,
            "system": _SYSTEM_PROMPT,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_OLLAMA_TIMEOUT) as resp:
                body = json.loads(resp.read().decode())
                text = body.get("response", "").strip()
                if text:
                    bucket.append(text)
        except Exception:
            pass

    for model in _OLLAMA_MODELS:
        bucket: list[str | None] = []
        t = threading.Thread(target=_call, args=(model, bucket), daemon=True)
        t.start()
        t.join(timeout=_OLLAMA_TIMEOUT + 0.2)  # wall-clock budget per model
        if bucket:
            return bucket[0]

    return None


# ---------------------------------------------------------------------------
# Pattern-matching fallback dictionary
# ---------------------------------------------------------------------------
# Each entry: (compiled_pattern, spooky_message)
# Patterns are matched case-insensitively against the full stderr string.
# First match wins.

_FALLBACK_PATTERNS: Sequence[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"ModuleNotFoundError|No module named", re.I),
        "The spirits cannot summon that module — run `pip install <name>` to appease them.",
    ),
    (
        re.compile(r"ImportError", re.I),
        "A cursed import rattles its chains — check your PYTHONPATH and installed packages.",
    ),
    (
        re.compile(r"command not found|is not recognized|not recognized as", re.I),
        "This command does not exist in the mortal realm — check your PATH or install the tool.",
    ),
    (
        re.compile(r"git:.*not found|git.*command", re.I),
        "Git has fled from your machine — install it and add it to PATH before the deadline haunts you.",
    ),
    (
        re.compile(r"SyntaxError|invalid syntax", re.I),
        "Your code reeks of forbidden syntax — a missing colon or bracket has unleashed chaos.",
    ),
    (
        re.compile(r"IndentationError|unexpected indent|unindent", re.I),
        "The indentation demons have struck — your spaces and tabs are at war with each other.",
    ),
    (
        re.compile(r"PermissionError|Permission denied|Access is denied", re.I),
        "The file screams 'FORBIDDEN' — try `sudo` or check ownership with `ls -la`.",
    ),
    (
        re.compile(r"FileNotFoundError|No such file or directory", re.I),
        "That file has vanished into the void — double-check the path, it may never have existed.",
    ),
    (
        re.compile(r"ConnectionRefusedError|Connection refused|ECONNREFUSED", re.I),
        "The server slammed its coffin shut — make sure the service is running and the port is right.",
    ),
    (
        re.compile(r"TimeoutError|timed out|ETIMEDOUT", re.I),
        "The network has ghosted you completely — check connectivity or increase the timeout.",
    ),
    (
        re.compile(r"KeyError", re.I),
        "You reached into the cauldron for a key that was never brewed — check your dict keys.",
    ),
    (
        re.compile(r"AttributeError", re.I),
        "You summoned an attribute that doesn't exist on this object — the spirit is confused.",
    ),
    (
        re.compile(r"TypeError", re.I),
        "You mixed potions that don't mix — wrong types were passed where the ghost expected something else.",
    ),
    (
        re.compile(r"ValueError", re.I),
        "The value you offered the ghost was unacceptable — check your inputs and expected ranges.",
    ),
    (
        re.compile(r"IndexError|list index out of range", re.I),
        "You reached beyond the edge of the list — the abyss has no index there.",
    ),
    (
        re.compile(r"RecursionError|maximum recursion depth", re.I),
        "Your function descended into the underworld and never came back — add a base case.",
    ),
    (
        re.compile(r"MemoryError|out of memory|OOM", re.I),
        "The memory cauldron is empty — your process consumed everything and still wanted more.",
    ),
    (
        re.compile(r"npm ERR!|node_modules", re.I),
        "Node's spirits are restless — try `npm install` or delete node_modules and start fresh.",
    ),
    (
        re.compile(r"ENOENT", re.I),
        "A file or directory has been spirited away — verify the path actually exists.",
    ),
    (
        re.compile(r"docker.*not found|Cannot connect to the Docker daemon", re.I),
        "Docker's daemon has escaped its container — start Docker Desktop and try again.",
    ),
    (
        re.compile(r"SSL|certificate verify failed|CERTIFICATE_VERIFY_FAILED", re.I),
        "The SSL specter blocks your path — your certificates may be expired or misconfigured.",
    ),
    (
        re.compile(r"exit code 1|exited with 1", re.I),
        "The command died with a non-zero scream — consult the output above for the true curse.",
    ),
]

_GENERIC_FALLBACK = (
    "An unknown phantom sabotaged your command — read the stderr carefully, the clue lurks within."
)


def _pattern_fallback(stderr_text: str) -> str:
    """Return the first matching spooky message, or the generic fallback."""
    for pattern, message in _FALLBACK_PATTERNS:
        if pattern.search(stderr_text):
            return message
    return _GENERIC_FALLBACK


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_spooky_diagnosis(stderr_text: str) -> str:
    """
    Return a one-sentence spooky diagnosis of *stderr_text*.

    Tries Ollama first (phi3 → llama3, 1.5 s timeout each).
    Falls back to pattern matching if Ollama is unreachable.

    Never raises — always returns a non-empty string.
    """
    if not stderr_text.strip():
        return _GENERIC_FALLBACK

    diagnosis = _try_ollama(stderr_text)
    if diagnosis:
        return diagnosis

    return _pattern_fallback(stderr_text)
