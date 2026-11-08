# SpookCLI — Kiroween 2026 demo video

Target length: **2:50** (hard cap 3:00).
Format: 1920×1080, 30 or 60 fps, H.264.
Voice: live narration or recorded voice-over — either works, but keep it loose.

The one-sentence pitch the video must land:

> **SpookCLI is a Halloween costume for your terminal — a ghost-summoning command
> wrapper with a live haunted process monitor underneath.**

---

## 1. Pre-flight checklist

Do this **before** you hit record. Most bad demo videos are setup failures.

- [ ] Run on a real desktop session (WSLg, X11, Windows, or macOS). Not headless.
- [ ] `spook` resolves in the recording shell (the project venv is active).
- [ ] Audio works: `spook test-ghost` plays the scream and shows the overlay.
      On Debian/Ubuntu/WSL: `sudo apt install libpulse0`.
- [ ] `spook run echo "hello"` succeeds and `spook run python -c "import sys; sys.exit(1)"` triggers the ghost.
- [ ] `spook gtop` opens and exits with `q` / `Esc`.
- [ ] Terminal font is **18–20 pt**, dark theme, no prompt clutter.
- [ ] Close Slack, Discord, browsers, and notifications. Disable Do Not Disturb.
- [ ] Hide desktop icons. Use a plain dark wallpaper.
- [ ] Arrange windows: terminal on the **left**, `gtop` on the **right**.
- [ ] Start `gtop` fresh so the crypt and candy counter are at their defaults.
- [ ] Record two rehearsals before the real take.

> Safety: only curse and exorcise the disposable demo processes below. Never
> select PID `0`, PID `1`, your shell, or `gtop` itself. The app blocks those,
> but the video should not look like it is trying.

---

## 2. Demo harness (disposable processes)

Create these three files in `/tmp`. They are safe to kill. The `prctl` calls
rename the processes on Linux so the table reads like a story; on Windows they
silently do nothing.

> **Record on Linux or WSLg if you can.** On Windows, `psutil.net_connections`
> may need an elevated shell to see other processes' ports, and the demo
> processes will all be named `python`. On macOS the rename fails harmlessly,
> so the names read as `Python`.

### `/tmp/gtop_demo_family.py` — hot parent + leaking child

```python
"""Demo: a hot parent with a slowly leaking child."""
import ctypes
import os
import subprocess
import sys
import time


def rename(name: str) -> None:
    try:
        ctypes.CDLL("libc.so.6").prctl(15, name.encode(), 0, 0, 0)  # PR_SET_NAME
    except Exception:
        pass


CHILD = """
import ctypes, time
try:
    ctypes.CDLL('libc.so.6').prctl(15, b'leak-child', 0, 0, 0)
except Exception:
    pass
buf = []
for _ in range(240):
    buf.append(bytearray(4_000_000))   # ~4 MB/s, ~960 MB total
    time.sleep(1)
"""

rename("haunt-root")
child = subprocess.Popen([sys.executable, "-c", CHILD])
print(f"FAMILY_ROOT={os.getpid()} LEAK_CHILD={child.pid}", flush=True)

# Keep the parent hot so it always appears in the visible table.
end = time.time() + 300
while time.time() < end:
    pass
```

### `/tmp/gtop_demo_port.py` — squatter on port 3000

```python
"""Demo: a harmless HTTP listener that gtop flags as a port squatter."""
import ctypes
import http.server
import socketserver

try:
    ctypes.CDLL("libc.so.6").prctl(15, b"port-squatter", 0, 0, 0)
except Exception:
    pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("0.0.0.0", 3000), http.server.SimpleHTTPRequestHandler) as httpd:
    print("port-squatter listening on :3000", flush=True)
    httpd.serve_forever()
```

### `/tmp/gtop_demo_burner.py` — the runaway CPU process

```python
"""Demo: a process that burns CPU so it stays visible in the table."""
import ctypes

try:
    ctypes.CDLL("libc.so.6").prctl(15, b"runaway-daemon", 0, 0, 0)
except Exception:
    pass

while True:
    pass
```

### Launch them

```bash
# Terminal B — port haunting
python3 /tmp/gtop_demo_port.py

# Terminal C — process family + leak (start ~20 s before recording)
python3 /tmp/gtop_demo_family.py

# Terminal D — curse victim
python3 /tmp/gtop_demo_burner.py
```

Then start the star of the show:

```bash
# Terminal A
spook gtop
```

Give it **10–15 seconds** before recording. The leak detector needs a few
snapshots (2 s each) before the `LEAK` tag appears.

**Validated values on Linux:** `port-squatter` appears immediately with a
`:3000` badge, `leak-child` earns its `LEAK` tag within roughly 6–10 seconds at
about 4 MB/s growth, and `haunt-root` plus `runaway-daemon` sit near 100% CPU.
The leak flag and the two hot processes keep all three demo rows in the visible
table.

> The leak child allocates up to ~960 MB over its four-minute run. Tear the
> harness down as soon as the take ends.

### Teardown (after the last take)

The family script prints `LEAK_CHILD=<pid>`. The child outlives its parent, so
clean it up explicitly:

```bash
# Ctrl-C each harness terminal, then:
pkill -f gtop_demo_port.py
pkill -f gtop_demo_family.py
pkill -f gtop_demo_burner.py

# If the leak child survived its parent (it keeps allocating for ~4 minutes):
kill -CONT <LEAK_CHILD_PID> 2>/dev/null
kill -9 <LEAK_CHILD_PID> 2>/dev/null
```

`kill -CONT` first is harmless when the process is running, and it rescues the
case where a crashed `gtop` left it frozen.

---

## 3. Recording setup (OBS or similar)

| Setting | Value |
|---|---|
| Canvas / output | 1920×1080 |
| FPS | 30 (60 if your machine is fast) |
| Scene | Display capture, cropped to the terminal + gtop area |
| Mic | Noise suppression on, gain set so peaks hit about −6 dB |
| Desktop audio | On, but duck the app under the voice |
| Music | Royalty-free spooky loop at −24 dB, or the app's own soundtrack |
| Cursor | Highlight clicks if your recorder supports it |
| Notifications | Off |

**Composition:** the gtop window is 480×820, so put it on the right third and
keep the terminal on the left two-thirds. In editing, do **1.4–1.6× punch-ins**
on the port badge, the cursed row, and the `LEAK` tag so viewers can read them
without squinting.

---

## 4. Shot list and script

Times are targets, not laws. Cut dead air aggressively.

### Scene 1 — Cold open (0:00–0:12)

**Visual:** Terminal. Type and run:

```bash
spook run python -c "import sys; sys.exit(1)"
```

The command fails; the ghost overlay screams and appears.

**Narration:**
> Every developer has that one command that refuses to work. Most tools print a
> stack trace. SpookCLI summons a ghost.

**On-screen text:** `SpookCLI — a haunted terminal`

---

### Scene 2 — The pitch (0:12–0:30)

**Visual:** Run a success:

```bash
spook run echo "hello world"
```

Then launch the monitor:

```bash
spook gtop
```

Let the window fade in.

**Narration:**
> It wraps your commands, scores your failures, and buries your kills in a
> crypt. And when the machine starts acting possessed, you open `gtop` — a live
> haunted process monitor.

---

### Scene 3 — gtop tour (0:30–0:55)

**Visual:** Point at each region as you name it:

1. CPU/RAM gauges.
2. Process table.
3. Kiro mascot.
4. Candy bucket — click it once (counter increments).
5. Flying Kiro — click it once (candy +3, ghost swarm).
6. Press `s` once for the shake + scream + swarm.

**Narration:**
> This is real `psutil` telemetry, every two seconds, on a background Qt thread.
> CPU is Core Heat. RAM is the Soul Pool. Kiro judges you. The bucket collects
> souls. And yes — pressing S summons ghosts.

**Tip:** do not explain every widget. Three seconds each is plenty.

---

### Scene 4 — Port Hauntings (0:55–1:20)

**Visual:**

1. Terminal B is already running `gtop_demo_port.py`.
2. In gtop, point at the row named `port-squatter` and its `:3000` badge.
3. Hover it — the ☠ button is already visible because it is a squatter.
4. Click ☠ once. The row vanishes; the crypt count ticks up.

**Narration:**
> Something is always squatting on port 3000. gtop maps every listening port to
> the process holding it, flags the usual suspects — 3000, 8080, 5432 — and
> gives you a one-click exorcism. No `lsof`, no `netstat`, no guessing.

**Punch-in:** the `:3000` badge and the ☠ button.

---

### Scene 5 — Curse / Uncurse (1:20–1:45)

**Visual:**

1. Select `runaway-daemon` in the table.
2. Press `c`. The row turns icy blue, the tag reads `(cursed)`, and it pins to
   the top of the table. Its CPU% drops to `0.0` as the process freezes.
3. Hold two seconds on the frozen row.
4. Press `c` again. The row thaws, sinks back into the normal order, and the
   CPU% climbs.

Optional proof shot: in a second terminal, `ps -o stat= -p <pid>` shows `T`
while cursed, then `R` after.

**Narration:**
> Sometimes you don't want to kill it — you want it to stop. Press C and the
> process is cursed: frozen mid-scream, its row turned to ice and pinned where
> you can always reach it. Press C again and it lurches back to life. And if you
> close gtop, every curse is lifted automatically.

**On-screen text:** `c = SIGSTOP / SIGCONT`

---

### Scene 6 — Trace Bloodline (1:45–2:15)

**Visual:**

1. Select `haunt-root`.
2. Press `Shift+T`.
3. The table collapses into a tree: `haunt-root` → `leak-child`, indented.
4. The banner appears: `BLOODLINE: haunt-root (PID …) · 1 kin · LEAK IN LINEAGE`.
5. `leak-child` carries the `LEAK` tag, and the root→leak path is highlighted.
6. Hold on the tree for three seconds.
7. Press `Shift+T` again to restore the full table.

**Narration:**
> Memory leaks are family business. Shift+T traces the bloodline of any process
> — the full descendant tree, generation by generation. gtop watches RSS growth
> over time, flags the one that keeps swelling, and lights up the branch that is
> leaking. That's the leak. That's its parent. Now you know what to exorcise.

**Punch-in:** the `LEAK` tag and the indented child row.

---

### Scene 7 — Built with Kiro (2:15–2:35)

**Visual:** fast cuts, about 5 seconds each:

1. `.kiro/specs/gtop-ui-spec.md` — scroll to sections 7–10.
2. `.kiro/steering/architecture-rules.md` — the process-control safety rules.
3. `.kiro/hooks/on_error.json`.
4. `.kiro/settings/mcp.json` — the Stitch MCP server entry.

**Narration:**
> The whole thing was built in Kiro. gtop started as a spec — layout, palette,
> and the safety rules that stop a process toy from freezing your machine.
> Steering enforced PyQt6, `psutil`, and thread safety. Hooks turn failed
> commands into ghost events. And the Stitch MCP server supplied the design.

**On-screen text:** `Specs · Steering · Hooks · MCP`

---

### Scene 8 — Close (2:35–2:50)

**Visual:** full gtop window, mascot taunting, then cut to the terminal:

```bash
spook gtop
```

End card:

```
SpookCLI
github.com/saveduser/spook-cli
MIT licensed · Built with Kiro
```

**Narration:**
> SpookCLI is a Halloween costume for your terminal — and a genuinely useful
> process monitor underneath. It's open source, MIT licensed, and waiting for
> your machine. `spook gtop`. Trick or treat.

---

## 5. Narration-only script (for recording voice-over)

Read this straight through. It is about 2:00 of speech, which leaves room for
pauses and visual beats.

> Every developer has that one command that refuses to work. Most tools print a
> stack trace. SpookCLI summons a ghost.
>
> It wraps your commands, scores your failures, and buries your kills in a
> crypt. And when the machine starts acting possessed, you open gtop — a live
> haunted process monitor.
>
> This is real psutil telemetry, every two seconds, on a background Qt thread.
> CPU is Core Heat. RAM is the Soul Pool. Kiro judges you. The bucket collects
> souls. And yes — pressing S summons ghosts.
>
> Something is always squatting on port 3000. gtop maps every listening port to
> the process holding it, flags the usual suspects — 3000, 8080, 5432 — and gives
> you a one-click exorcism. No lsof, no netstat, no guessing.
>
> Sometimes you don't want to kill it — you want it to stop. Press C and the
> process is cursed: frozen mid-scream, its row turned to ice and pinned where
> you can always reach it. Press C again and it lurches back to life. And if you
> close gtop, every curse is lifted automatically.
>
> Memory leaks are family business. Shift+T traces the bloodline of any process
> — the full descendant tree, generation by generation. gtop watches RSS growth
> over time, flags the one that keeps swelling, and lights up the branch that is
> leaking. That's the leak. That's its parent. Now you know what to exorcise.
>
> The whole thing was built in Kiro. gtop started as a spec — layout, palette,
> and the safety rules that stop a process toy from freezing your machine.
> Steering enforced PyQt6, psutil, and thread safety. Hooks turn failed commands
> into ghost events. And the Stitch MCP server supplied the design.
>
> SpookCLI is a Halloween costume for your terminal — and a genuinely useful
> process monitor underneath. It's open source, MIT licensed, and waiting for
> your machine. spook gtop. Trick or treat.

---

## 6. Editing notes

- Cut every pause longer than ~0.4 s. The video should feel faster than reality.
- Add a short lower-third at 0:30: `spook gtop — Haunted Process Monitor`.
- Add small labels when a feature first appears: `PORT HAUNTINGS`, `CURSE`,
  `TRACE BLOODLINE`.
- Keep the app's own sounds audible but under the voice. The scream is part of
  the costume.
- Do not add copyrighted music. Use a royalty-free track or the app's own audio.
- **Hard-check the runtime before export.** If it is over 3:00, cut Scene 3
  first, then the optional `ps` proof shot.
- Export: H.264, 1080p, 30 fps, 8–12 Mbps, AAC 192 kbps.

---

## 7. Upload and submit

1. Upload to YouTube.
2. Title: `SpookCLI — a haunted terminal & process monitor (Kiroween 2026)`.
3. Visibility: **Public** (the rules require a public video).
4. Description:

   ```
   SpookCLI is a Halloween-themed CLI wrapper that summons ghosts when your
   commands fail — and gtop, a live haunted process monitor with port
   hauntings, curse/uncurse, and bloodline leak tracing.
   Built with Kiro: specs, steering, hooks, and the Stitch MCP server.
   Repo: https://github.com/saveduser/spook-cli
   ```

5. Add the YouTube URL to the Devpost submission.
6. Paste `docs/kiro-usage.md` into the write-up and attach
   `docs/screenshots/gtop.png`.

---

## 8. If something breaks on camera

| Problem | Recovery |
|---|---|
| Audio is silent | Keep going; add the app sounds in post, or lean on the voice-over. |
| `LEAK` tag has not appeared yet | Wait 6–8 more seconds; the detector needs three samples. |
| Port squatter missing | Restart `gtop_demo_port.py`; it must bind `:3000`. |
| Cursed process does not freeze | You selected a protected PID. Select `runaway-daemon` and try again. |
| A process is still frozen after a gtop crash | `kill -CONT <pid>`, or reopen gtop and press `c` on it. Never `kill -9` a process you have not identified. |
| gtop crashes | Restart it; the demo processes keep running. Resume the take from the scene you were on. |
| A take runs long | Cut Scene 3's bucket/flying-Kiro clicks. The core story is ports → curse → trace. |

---

## 9. Optional 30-second cut (social / thumbnail trailer)

1. Ghost scream + overlay (0–3 s).
2. `spook gtop` opens (3–7 s).
3. Port badge + click ☠ (7–12 s).
4. Press `c`, row turns icy, CPU drops (12–18 s).
5. `Shift+T`, tree + `LEAK` tag (18–26 s).
6. End card + `spook gtop` (26–30 s).

No narration needed — captions and the app's own sounds carry it.
