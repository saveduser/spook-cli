"""
Ghost event system — stubs for Phase 2 sound + visual effects.

Replace the bodies of these functions with real pygame / PyQt6 logic
once assets are ready. The CLI layer only calls trigger_ghost_event(),
so the interface is stable.
"""

from __future__ import annotations

import sys


def _play_sound(sound_file: str) -> None:
    """
    STUB: Play a spooky sound via pygame.

    Example real implementation:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(sound_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    """
    print(f"  [ghost/sound] Would play: {sound_file}  (stub)", file=sys.stderr)


def _show_ghost_overlay() -> None:
    """
    STUB: Launch a transparent PyQt6 overlay with a ghost animation.

    Example real implementation:
        from PyQt6.QtWidgets import QApplication, QLabel
        from PyQt6.QtCore import Qt, QTimer
        app = QApplication(sys.argv)
        label = QLabel("👻")
        label.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        label.setStyleSheet("font-size: 120px;")
        label.show()
        QTimer.singleShot(3000, app.quit)
        app.exec()
    """
    print("  [ghost/overlay] Would show ghost overlay  (stub)", file=sys.stderr)


def trigger_ghost_event() -> None:
    """
    Entry point called by the CLI on non-zero exit codes.

    Orchestrates all spooky side-effects. Swap stubs for real
    implementations in _play_sound() and _show_ghost_overlay().
    """
    print("\n[GHOST] A ghost has been summoned by your failure...", file=sys.stderr)
    _play_sound("assets/ghost_scream.wav")
    _show_ghost_overlay()
