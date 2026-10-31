# Feature Spec: Ghost Overlay & Exorcism Mechanic

## Goal
Spawn interactive floating ghost sprites upon command failure and allow the user to drag or click them into a pumpkin bucket in the bottom right corner.

## Requirements
1. Capture exit code from sub-process shell command.
2. If non-zero, trigger `GhostOverlayWindow`.
3. Animate ghost across bounds using `QTimer`.
4. Play `assets/spooky_spawn.wav` on trigger.
5. On mouse click/drag collision with pumpkin bucket:
   - Play `assets/ghost_caught.wav`.
   - Close overlay window.