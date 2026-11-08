# How SpookCLI was built with Kiro

SpookCLI is not "a project that happens to have a `.kiro` folder". The agent
substrate drove the architecture, the visual language, and the safety rules that
keep a process-monitoring toy from freezing your machine.

## 1. Specs first

| Spec | What it locked down |
|---|---|
| `.kiro/specs/gtop-ui-spec.md` | Frameless `QMainWindow`, `WA_TranslucentBackground`, fixed `480x820`, glass panel `rgba(15, 20, 28, 180)`, the gauge/table/crypt layout, and the Port Hauntings / Curse / Trace Bloodline contracts |
| `.kiro/specs/system-whispers-spec.md` | The non-blocking `whispers.py` probe loop that turns CPU/RAM/zombie anomalies into speech-bubble taunts |

The gtop spec is the implementation contract: every feature in the shipped app
maps to a numbered section, including the safety guards. When the three
haunting features were added, the spec grew first and the code followed.

## 2. Steering that changed the output

- **`architecture-rules.md`** forced the PyQt6-only stack (no `curses`,
  `tkinter`, or `textual`), `QThread` polling, and `psutil`-only OS data. It is
  why `gtop` uses a `SnapshotWorker` emitting `SystemSnapshot` objects instead
  of a blocking loop.
- **`cross-platform-rules.md`** produced the audio sentinel, the UTF-8 stdout
  reconfigure in `board.py`, and the port-permission fallback. `net_connections`
  raising `AccessDenied` is treated as "no ports", never as a crash.
- **`aesthetic-guidelines.md`** fixed the palette: `#0B0813` base, `#38254A`
  borders, `#FF7A00` CPU, `#39FF14` RAM, `#BD00FF` phantom. The icy
  `#7DE9FF` curse state was added to the palette rather than invented ad hoc.
- **`architecture-rules.md` §5 (Process Control Safety)** is the reason Curse
  refuses PID `0`, PID `1`, and the gtop process itself, resumes a cursed
  process before `terminate()`, and resumes every curse in `closeEvent`.

## 3. MCP: Stitch design source

`.kiro/settings/mcp.json` configures the Stitch MCP server. The gtop layout —
glass panel, pumpkin bucket, Kiro mascot, gauge cards, and the
`HAUNTED PROCESS` table — was derived from the Stitch project recorded in the
spec, then implemented directly in PyQt6. The right-hand "Audio & Interaction
Blueprint" panel was explicitly excluded by the spec.

## 4. Hooks

`.kiro/hooks/on_error.json` registers a `command_failed` hook. When a command
fails under `spook run`, the hook path drives the ghost event: scream, overlay,
and an AI diagnosis bubble. The same event path is available manually via
`spook test-ghost`.

## 5. Verify the evidence

```bash
# The specs and steering that shaped the build
find .kiro -type f | sort

# Where each feature lives
grep -n "HAUNTED_PORTS\|_toggle_curse\|_toggle_trace\|_detect_leak" spookcli/gtop.py

# The safety invariants
grep -n "closeEvent\|FORBIDDEN RITUAL\|resume()" spookcli/gtop.py
```

## 6. What the agent did not do

The agent did not get unsupervised process control. Exorcise and Curse are
guarded, every `psutil` call degrades gracefully, and the window resumes all
curses on exit. That constraint is part of the design, not a cleanup pass.
