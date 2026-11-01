# 🎃 SpookCLI

> A Halloween-themed CLI wrapper that summons ghosts when your commands fail.

## Quick Start

```powershell
# 1. Create an isolated virtual environment with uv
cd spookcli
uv venv

# 2. Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate


# 3. Install the project and its dependencies
uv pip install -e .

# 4. Run a command through SpookCLI
spook run echo "hello world"            # success  ✅
spook run python -c "import sys; sys.exit(1)"   # failure 💀
spook gtop                              # haunted process monitor
```

## Usage

```
spook run <command> [args...]
spook gtop
```

## Project Structure

```
spookcli/
├── pyproject.toml          # project metadata & dependencies
├── README.md
└── spookcli/
    ├── __init__.py
    ├── cli.py              # click entrypoint — `spook run`, `spook gtop`
    ├── runner.py           # subprocess wrapper, real-time streaming
    ├── board.py            # scoreboard and kill ledger
    ├── ghost.py            # ghost event audio + Qt overlay
    ├── gtop.py             # PyQt6 haunted process monitor
    ├── whispers.py         # rotating Kiro prophecies
    └── assets/             # packaged GIF, PNG, WAV, and MP3 assets
        ├── ghost-kiro-blink.gif
        ├── pumpkin.png
        ├── ghost_scream.wav
        ├── collected.wav
        ├── exorcism1.wav
        ├── exorcism2.wav
        ├── Ghost_in_the_Cabinet.mp3
        └── Possessed_High_Score.mp3
```

## Ghost Effects

`spookcli/ghost.py` owns the failure overlay:

| Component | Library | Behaviour |
|---|---|---|
| `_play_sound()` | `pygame` | Loads `spookcli/assets/ghost_scream.wav`; silently no-ops if audio is unavailable |
| `_show_ghost_overlay()` | `PyQt6` | Frameless, translucent Kiro overlay with speech bubble and auto-dismiss |

## Linux audio & emoji fonts

`gtop` and the ghost overlay fall back to silent mode when no audio device is
available. For PulseAudio support and colour emoji glyphs on Debian/Ubuntu/WSL:

```bash
sudo apt install libpulse0 fonts-noto-color-emoji
```

The app ships its own GIF/PNG mascot and pumpkin assets inside the wheel, so the
UI still renders without emoji fonts.

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `click` | 8.1.8 | CLI parsing, coloured output |
| `pygame` | 2.6.1 | Optional audio playback |
| `PyQt6` | 6.8.1 | `gtop` and ghost overlay |
