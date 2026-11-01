# SpookCLI Cross-Platform Invariants

1. **Execution Pathing:** Always use `sys.executable -m spookcli.cli` for background spawning to avoid virtual environment `PATH` issues.
2. **Audio Sentinel:** All audio calls (`pygame.mixer`) MUST be gated behind a `_AUDIO_AVAILABLE` try/except block to prevent crashes on headless Linux or WSL environments without ALSA drivers.
3. **File I/O:** All reads/writes to `~/.spookcli_stats.json` must degrade gracefully. If the file is locked, corrupt, or read-only, the application must swallow the error and continue UI rendering.
4. **ANSI Windows Support:** `board.py` must reconfigure `sys.stdout` to UTF-8 on Windows at module import time to ensure CP437 boxes render correctly in PowerShell.