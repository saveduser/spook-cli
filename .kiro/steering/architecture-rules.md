# Architectural Steering & Invariants

When generating or refactoring code for SpookCLI / gtop, you MUST adhere to the following constraints:

1. **Framework Strictness:**
   - Visual UI is built with `PyQt6`. `gtop` uses a frameless `QMainWindow` with `WA_TranslucentBackground` and a glassmorphic central panel.
   - DO NOT import or use `curses`, `tkinter`, `textual`, or raw blocking `input()` loops.
   - Use Qt signals/slots, `QThread`, and `QTimer`. Never run polling or `time.sleep()` on the GUI thread.
   - `pygame` is permitted only for optional audio and must fail gracefully when no audio device or module is available.

2. **Cross-Platform Safety (`psutil` First):**
   - For all OS-level data (CPU, RAM, PIDs), you MUST use `psutil`.
   - DO NOT use `subprocess.run` to call `ps`, `top`, or `tasklist`.
   - All data fetching must degrade gracefully (e.g., wrap `psutil.AccessDenied` in try/except blocks and skip the process).

3. **Concurrency:**
   - Long-running data polling must occur in a `QThread` or daemon `threading.Thread`. Emit snapshots back to the GUI thread with Qt signals.
   - Never block the Qt event loop with synchronous polling.

4. **Design Assets:**
   - Use local files from `spookcli/assets/` so they ship inside the wheel. The gtop mascot prefers `blinking_ghost.gif` and falls back to `ghost-kiro-blink.gif`, then a procedural ghost.
   - Implement only the left-hand gtop application panel. The right-hand Audio & Interaction Blueprint HUD is excluded.

5. **Process Control Safety:**
   - Exorcise (`SIGTERM`) must refuse PID `0`, PID `1`, and `os.getpid()`. The same guard applies to Curse (`SIGSTOP`).
   - Curse state lives in `GtopWindow._cursed_pids`. Every path that removes a curse (toggle, exorcise, window close) must call `resume()` inside try/except.
   - `closeEvent` MUST resume all cursed PIDs before stopping the snapshot worker, or the user is left with a frozen process.
   - A cursed process must be resumed before `terminate()`; `SIGTERM` is not delivered while the process is stopped.

6. **Port Telemetry:**
   - Port mapping uses `psutil.net_connections(kind="inet")` only. Never shell out to `lsof`, `ss`, or `netstat`.
   - `net_connections` commonly raises `AccessDenied` on Windows and restricted Linux; treat that as "no ports", never as a fatal error.
   - Only the curated `HAUNTED_PORTS` set earns a squatter badge, so system listeners like sshd are not mislabelled.

7. **Leak Heuristics:**
   - RSS history is owned by `SnapshotWorker`, not the GUI thread.
   - Growth detection wins over the highest-RSS fallback. Only growth-based leaks may drive mascot taunts.
