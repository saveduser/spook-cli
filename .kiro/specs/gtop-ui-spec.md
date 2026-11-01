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
- **Process Table:** `PID | HAUNTED PROCESS | CPU% | MEM% | ACT`, custom scrollable rows, CPU/memory threshold colouring, selection, and hover-revealed exorcise button.
- **Crypt:** Slain processes with signal labels and a `⚡ Resurrect` action.
- **Footer:** `k` Exorcise, `r` Resurrect, `s` Spook, `m` Mute, plus audio-engine status.
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
- Poll CPU, RAM, core count, process rows, and zombies with `psutil` every 2 seconds.
- Run collection in a `QThread`, emitting snapshots to the GUI thread.
- Start the whisper poller via `start_whispers()` and consume `get_current_whispers()` without blocking.
- Wrap every `psutil` and audio call in try/except and degrade gracefully.

6. **Interactions**
- Header drag moves the frameless window; gray dot minimizes, purple dot summons a ghost swarm, orange dot closes.
- `k` sends SIGTERM to the selected process, adds it to the crypt, plays an exorcism sound, and increments treats.
- `r` releases the newest crypt soul; `s` plays a scream, shakes the window, and summons ghosts; `m` toggles audio.
- `Up`/`Down` navigates the process table; `q`/`Esc` exits cleanly and stops the worker.
