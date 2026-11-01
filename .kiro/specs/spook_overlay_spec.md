# Feature Spec: Ghost Overlay & Exorcism Mechanic

## 1. Goal
Spawn interactive floating ghost sprites upon non-zero shell command exit codes, providing a tactile, gamified "exorcism" mechanic where the user drags or clicks the ghost into a pumpkin bucket UI element to dismiss it.

## 2. Requirements & Architecture

### A. Subprocess Hook & Trigger
- **Exit Code Capture:** Shell hooks capture non-zero exit codes ($?) from terminal commands.
- **Background Spawning:** Triggers the background worker via `sys.executable -m spookcli.cli _ghost-overlay` using a detached session/process flag.

### B. PyQt6 Transparent Overlay (`GhostOverlayWindow`)
- **Frameless & Transparent:** Renders as a full-screen or floating transparent window (`Qt.WindowType.FramelessWindowHint`, transparent background).
- **Animation Loop (`QTimer`):** 
  - Drives smooth floating trajectory updates for the ghost sprite across screen bounds.
  - Handles QMovie / frame-by-frame sprite animations.

### C. Audio Integration
- **Spawn Sound:** Play `assets/ghost_scream.wav` asynchronously via Pygame mixer upon overlay initialization (with headless/WSL fault-tolerant sentinel checks).
- **Exorcism Sound:** Play `assets/exorcism1.wav`or `exorcism2.wav` immediately upon successful collision/interaction.

### D. The Pumpkin Bucket Exorcism Mechanic
- **Target Zone:** A fixed bounding box representing the "Pumpkin Bucket" rendered in the bottom-right corner of the overlay.
- **Mouse Interaction:** 
  - Supports click-to-banish or drag-and-drop collision detection.
  - When the ghost sprite's bounding box intersects the pumpkin bucket zone on mouse release/click:
    1. Trigger `exorcism1.wav` or `exorcism2.wav`.
    2. Execute a brief dissolve or shrink animation.
    3. Terminate the PyQt application loop (`app.quit()`), closing the overlay instantly.
    4. **The Ghost's Voice (System Whispers Integration)**
      - **Speech Bubble UI:** A PyQt6 `QLabel` positioned directly above the ghost sprite. Must be styled with transparent background, soft off-white text (`#E2E8F0`), and a subtle Ethereal Cyan (`#00F2FE`) border.
      - **Update Loop:** A `QTimer` firing every 3 seconds calls `spookcli.whispers.get_current_whispers()` and updates the `QLabel` text.
      - **Behavior:** The speech bubble must move *with* the ghost during the drag-and-drop exorcism interaction, never detaching from the sprite.