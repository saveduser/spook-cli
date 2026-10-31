# SpookCLI Architectural Guidelines

- **Core Goal**: CLI wrapper in Python (`spook run <command>`) that triggers desktop ghost overlays when exit code != 0.
- **Tech Stack**: Python 3.10+, PyQt6 (Overlay engine), Pygame (Audio effects).
- **UI Constraints**: The overlay window MUST use `Qt.WindowType.FramelessWindowHint` and `Qt.WindowType.WindowStaysOnTopHint` with a transparent background.
- **Rules**: Keep dependencies minimal. Ensure terminal fallback logging if PyQt or asset loading fails gracefully.