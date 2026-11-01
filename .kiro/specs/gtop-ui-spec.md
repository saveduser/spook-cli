# Feature Spec: gtop (Haunted Textual Process Monitor)

1. **Goal**
A cross-platform terminal process monitor built with `textual`. It features a standard process data table on the base layer, with absolute-positioned ASCII ghosts floating on a higher z-index that taunt the user based on live system metrics.

2. **UI Architecture (Textual)**
- **Base Layer (z-index: 1):** A `DataTable` widget displaying PID, NAME, CPU%, and MEM%. Updated every 2 seconds via `spookcli.whispers`.
- **Ghost Layer (z-index: 10):** A full-screen, transparent Textual `Container` using absolute positioning.
- **The Mascots:** Spawn Kiro ghost ASCII sprites as `Static` widgets inside the Ghost Layer. 

3. **Aesthetic & CSS Guidelines**
- **Colors:**
  - Base Terminal: Slate Gray (`#2A3442`) and Soft Off-White (`#E2E8F0`).
  - Ghost 1 (Memory): Ectoplasm Green (`#00FF66`).
  - Ghost 2 (CPU): Neon Orange (`#FF5E00`).
  - Ghost 3 (Zombie): Phantom Purple (`#B026FF`).
- **Animation:** Use Textual's `widget.styles.animate("offset", ...)` to slowly move the ghosts across the terminal screen bounds over 10-15 second durations. Also the ghosts should be varying in sizes, we acn have more than 3 ghosts. Depening on resource usage by a process number of ghosts will increase.

4. **Dialogue Engine Integration**
- The ghosts must display short speech bubbles (e.g., `"Mmmm... 4GB of tasty Chrome"`) derived from the `whispers.py` psutil data feed.