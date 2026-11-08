# Feature Spec: gtop (Haunted PyQt6 Process Monitor)

## Design Source (Stitch MCP)
- **Project URL:** `https://stitch.withgoogle.com/projects/8216542245551026445?node-id=c914e054770c442f9bb6729f609a4b80`
- **Reference Asset:** Prefer `spookcli/assets/blinking_ghost.gif` for the mascot, falling back to `spookcli/assets/ghost-kiro-blink.gif`. Use `spookcli/assets/pumpkin.png` for the candy bucket.
- **Exclusion:** Ignore the right-hand "Audio & Interaction Blueprint" panel in the design; only implement the left-hand application UI.

1. **Goal**
A frameless, glassmorphic desktop process monitor driven by live `psutil` telemetry. It combines a process table with a taunting Kiro mascot, CPU/RAM gauges, a soul-candy bucket, and a crypt for slain processes.

2. **UI Architecture (PyQt6)**
- **Window:** `QMainWindow` with `Qt.WindowType.FramelessWindowHint`, `WA_TranslucentBackground`, fixed `480x820` size, and header drag support.
- **Glass Panel:** Central panel QSS uses `background-color: rgba(15, 20, 28, 180);`, a `#38254A` border, and a 14px radius.
- **Header:** Pulse dot, `GTOP` brand, `🎃 ALL HALLOWS' EVE` badge, live CPU/RAM values, animated audio toggle, and minimize/spook/close dots.
- **Candy Banner:** Pumpkin bucket, `HARVEST READY`, soul counter starting at `666`, and a `BOO!` button.
- **Mascot Panel:** `QLabel` + looping `QMovie` for Kiro, halo, `kiro.daemon` tag, and a dynamic speech bubble fed by `whispers.get_current_whispers()` and snapshot taunts.
- **Flying Kiro Patrol:** An independent `FlyingKiro` actor drifts across the full window on an 18s loop with a spectral aura, subtle rotation/scale, and a `KIRO (PATROL)` badge. Clicking it grants candy and summons a mini swarm.
- **Gauges:** Two-column CPU (`#FF7A00`) and RAM (`#39FF14`) bars with animated fills, core count, and overflow status.
- **Process Table:** `PID | HAUNTED PROCESS | CPU% | MEM% | ACT`, custom scrollable rows, CPU/memory threshold colouring, selection, hover-revealed exorcise button, port-squatter badges, and tree indentation during a bloodline trace.
- **Trace Banner:** Hidden by default. When a trace is active it shows `BLOODLINE: <name> (PID) · <n> kin`, a leak warning, and a close button.
- **Crypt:** Slain processes with signal labels and a `⚡ Resurrect` action.
- **Footer:** `k` Exorcise, `c` Curse, `T` Trace, `r` Resurrect, `s` Spook, `m` Mute, plus audio-engine status.
- **Excluded:** The right-hand developer HUD is not implemented.

3. **Aesthetic Guidelines**
- Base `#0B0813`; panel `#120B1D`; border `#38254A`; text `#F1F5F9`; muted `#A89CB9`.
- CPU accent `#FF7A00`; RAM accent `#39FF14`; phantom/selection accent `#BD00FF`.
- Fonts: Fira Code / monospace, with emoji glyphs for Halloween accents.
- Decorations: subtle scanlines and spiderweb corners, but all interactive content must remain crisp.

4. **Dialogue Engine Integration**
- The mascot displays short speech-bubble taunts derived from `whispers.py` psutil anomalies and the current snapshot (zombie, CPU glutton, RAM glutton, or idle).
- Clicking Kiro, the flying patrol Kiro, or `poke kiro 🍬` cycles spectral prophecies; killing a process adds its soul to the crypt and increments the candy counter.

5. **Data & Concurrency**
- Poll CPU, RAM, core count, process rows, zombies, parent PIDs, thread counts, RSS, and listening ports with `psutil` every 2 seconds.
- Keep a full `all_processes` list plus a truncated `MAX_PROCS` visible list, so descendants can be traced even when they fall outside the table.
- Run collection in a `QThread`, emitting snapshots to the GUI thread. RSS history is owned by the worker thread.
- Start the whisper poller via `start_whispers()` and consume `get_current_whispers()` without blocking.
- Wrap every `psutil` and audio call in try/except and degrade gracefully.

6. **Interactions**
- Header drag moves the frameless window; gray dot minimizes, purple dot summons a ghost swarm, orange dot closes.
- `k` sends SIGTERM to the selected process, adds it to the crypt, plays an exorcism sound, and increments treats. A cursed process is resumed before termination so the signal is deliverable.
- `r` releases the newest crypt soul; `s` plays a scream, shakes the window, and summons ghosts; `m` toggles audio.
- `Up`/`Down` navigates the process table; `q`/`Esc` exits cleanly, resumes every cursed process, and stops the worker.

7. **Port Hauntings**
- Map listening TCP ports to owning PIDs with `psutil.net_connections(kind="inet")`, filtered to `CONN_LISTEN`.
- Haunted ports: `8080` (web), `3000` (dev), `5432` (postgres), `8000` (http), `5173` (vite), `3306` (mysql), `6379` (redis).
- A squatter row renders a compact `:port` badge and keeps its ☠ Exorcise button visible without hover.
- Squatters sort ahead of other processes so the haunting is always visible in the table.
- `net_connections` is wrapped in try/except and returns `{}` when the OS denies access; the rest of the monitor keeps working.

8. **Curse / Uncurse**
- `c` toggles `psutil.Process.suspend()` / `.resume()` for the selected process.
- Cursed rows use the icy accent `#7DE9FF` for the background tint, left border, PID, name, and dot, and show a `(cursed)` tag.
- Cursed PIDs live in `GtopWindow._cursed_pids`; the set is pushed into `ProcessTable.set_cursed_pids()` for immediate repaint.
- Cursed rows are pinned to the top of the visible table. A suspended process falls to 0% CPU and would otherwise drop out of the `MAX_PROCS` window, stranding the curse until exit.
- PID `0`, PID `1`, and the `gtop` process itself are protected and cannot be cursed.
- `closeEvent` resumes every cursed PID before stopping the worker, so exiting `gtop` never leaves a process frozen.

9. **Trace Bloodline**
- `Shift+T` toggles a full descendant tree for the selected process, built from `all_processes` by `ppid`.
- The tree is depth-first, capped at `TRACE_MAX_ROWS` (80), and sorted by CPU then memory within each generation.
- Rows are indented 11px per generation; the active root is the selected PID.
- The trace banner reports the root, descendant count, and whether a suspected leak is inside the lineage.
- If the leaking PID is in the tree, the path from root to leak is highlighted with the icy accent.
- Toggling `Shift+T` again, pressing the banner close button, or losing the root clears the trace and restores the normal table.
- Toggling a new root while tracing retargets the tree to the newly selected process.

10. **Leak Detection**
- Maintain a per-PID `deque` of RSS MB samples (`LEAK_WINDOW = 8`).
- A process is a growth leak when its RSS climbs at least `LEAK_GROWTH_MB` (12 MB) over the window; the fastest grower wins.
- If nothing is climbing, fall back to the largest resident process above `LEAK_FALLBACK_MB` (250 MB) as a suspected leak.
- The `gtop` process itself is excluded from leak candidates.
- Leak rows carry a `LEAK` tag and a purple accent; only growth-based leaks trigger the mascot taunt, so the highest-RSS fallback does not spam the speech bubble.
