# SpookCLI Cross-Platform Invariants

1. **Execution Pathing:** Always use `sys.executable -m spookcli.cli` for background spawning to avoid virtual environment `PATH` issues.
2. **Audio Sentinel:** All audio calls (`pygame.mixer`) MUST be gated behind a `_AUDIO_AVAILABLE` try/except block to prevent crashes on headless Linux or WSL environments without ALSA drivers.
3. **File I/O:** All reads/writes to `~/.spookcli_stats.json` must degrade gracefully. If the file is locked, corrupt, or read-only, the application must swallow the error and continue UI rendering.
4. **ANSI Windows Support:** `board.py` must reconfigure `sys.stdout` to UTF-8 on Windows at module import time to ensure CP437 boxes render correctly in PowerShell.
5. **Suspend/Resume:** Curse uses `psutil.Process.suspend()` / `.resume()`, which maps to `SIGSTOP`/`SIGCONT` on POSIX and `SuspendThread`/`ResumeThread` on Windows. Both can raise `AccessDenied`; surface a taunt and leave the curse set unchanged.
6. **Port Permissions:** `psutil.net_connections(kind="inet")` may raise `AccessDenied` or return entries with `pid=None` (especially Windows). Skip those entries; never abort the snapshot.
7. **Exit Hygiene:** Resuming cursed PIDs on `closeEvent` must never block shutdown. Wrap each resume individually, and continue even if one fails.