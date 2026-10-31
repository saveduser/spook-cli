# 🎃 SpookCLI

> A Halloween-themed CLI wrapper that summons ghosts when your commands fail.

## Quick Start

```powershell
# 1. Create an isolated virtual environment with uv
cd spookcli
uv venv

# 2. Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1

# 3. Install the project and its dependencies
uv pip install -e .

# 4. Run a command through SpookCLI
spook run echo "hello world"            # success  ✅
spook run python -c "import sys; sys.exit(1)"   # failure 💀
```

## Usage

```
spook run <command> [args...]
```

## Project Structure

```
spookcli/
├── pyproject.toml          # project metadata & dependencies
├── README.md
├── assets/
│   └── ghost_scream.wav    # (add your own spooky sound here)
└── spookcli/
    ├── __init__.py
    ├── cli.py              # click entrypoint — `spook run`
    ├── runner.py           # subprocess wrapper, real-time streaming
    └── ghost.py            # ghost event stubs (sound + Qt overlay)
```

## Phase 2 — Real Ghost Effects

Replace the stubs in `spookcli/ghost.py`:

| Stub | Library | What to implement |
|---|---|---|
| `_play_sound()` | `pygame` | Load + play `assets/ghost_scream.wav` |
| `_show_ghost_overlay()` | `PyQt6` | Frameless, translucent 👻 overlay for 3 s |

Both libraries are already declared as dependencies in `pyproject.toml`.

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `click` | 8.1.8 | CLI parsing, coloured output |
| `pygame` | 2.6.1 | Audio playback (Phase 2) |
| `PyQt6` | 6.8.1 | GUI ghost overlay (Phase 2) |
