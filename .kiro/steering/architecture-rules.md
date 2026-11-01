# Architectural Steering & Invariants

When generating or refactoring code for SpookCLI / gtop, you MUST adhere to the following constraints:

1. **Framework Strictness:** 
   - The UI is exclusively built using `textual>=0.40.0`. 
   - DO NOT import or use `curses`, `PyQt6`, `pygame`, `tkinter`, or raw blocking `input()` loops.
   - UI updates must use Textual's reactive properties or message queue, never `time.sleep()` in the main thread.

2. **Cross-Platform Safety (`psutil` First):**
   - For all OS-level data (CPU, RAM, PIDs), you MUST use `psutil`.
   - DO NOT use `subprocess.run` to call `ps`, `top`, or `tasklist`. 
   - All data fetching must degrade gracefully (e.g., wrap `psutil.AccessDenied` in try/except blocks and skip the process).

3. **Concurrency:**
   - Long-running data polling must occur in Python daemon `threading.Thread` or Textual `WORKER` threads (`@work`). Never block the main Textual app event loop.