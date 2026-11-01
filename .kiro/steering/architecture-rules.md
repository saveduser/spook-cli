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
