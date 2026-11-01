# Feature Spec: System Whispers (Live OS Taunts)

1. **Goal**
A cross-platform, non-blocking module (`spookcli/whispers.py`) that monitors live system resources using `psutil` and translates spikes into thematic "paranormal" strings.

2. **Integration Target: The Ghost Overlay**
- **Do NOT** integrate into `board.py` (the TUI blocks on `input()`, ruining the live feel).
- **Target:** Feed the output into `ghost.py`. The PyQt6 ghost will use these strings to "taunt" the user via a speech bubble while they attempt to exorcise it.

3. **Architecture Constraints**
- **Module:** `spookcli/whispers.py` runs a daemon thread updating a thread-safe list of active whispers.
- **Probes (psutil & os):**
  - *Possession:* CPU > 75% -> `[WARNING] {name} is demonically possessing the CPU ({cpu}%)`
  - *Poltergeist:* RAM > 15% -> `[ALERT] A Poltergeist is hoarding system memory ({name} at {mem}%)`
  - *Restless Spirits:* Zombie processes via `psutil` STATUS_ZOMBIE.
  - *Abandoned Tim