# Feature Spec: Retro BBS Terminal (spook board)

1. **Goal**
A 1990s-style Bulletin Board System TUI utilizing a "Soft Tech-Wear" aesthetic (Slate Gray, Soft Off-White, Ethereal Cyan) that visualizes JSON telemetry of failed commands, allowing users to resurrect dead commands and track live OS "hauntings."

2. **UI & Rendering Constraints**
- **Format:** Raw ANSI escape codes and CP437 single/double-line box characters.
- **Output:** Written directly to `sys.stdout`. Reconfigure to UTF-8 on Windows.
- **Panels Required:** Ghost Banner (using Kiro mascot), Cemetery (histogram), Haunt Log (recent failures), and the new **System Whispers Ticker** (footer).

3. **Interactive "Resurrection" Mechanic**
- The Haunt Log displays indexed failed commands `[1] - [7]`.
- Input loop intercepts numeric inputs (1-7).
- Triggers an Ethereal Cyan prompt: `⟡ ❯❯ Enter incantation (fix) for: <command>`
- Executes via `subprocess.run(shell=True)`.
- **Success:** Plays `assets/ghost_caught.wav`, updates `~/.spookcli_stats.json` status to `resurrected`, plays a 3-frame ASCII dissolve animation, and re-renders.

4. **System Whispers Ticker (Footer)**
- A single-line scrolling ticker at the bottom of the TUI.
- Displays local OS anomalies (Zombies, Detached HEADs, Memory Hogs) fetched asynchronously by the `whispers.py` module.