"""
Ghost event system — audio + PyQt6 visual overlay.

Public API (called by cli.py):
    trigger_ghost_event()        orchestrates sound + overlay

Internal layout:
    _play_sound(path)            pygame audio (non-blocking, try/except wrapped)
    _show_ghost_overlay()        launches the PyQt6 overlay and blocks until done
    _load_movie(path, w, h)      load animated GIF → QMovie, or None on failure
    _load_pixmap(path, w, h)     load PNG/static image → QPixmap, or None on failure
    GhostWidget                  QLabel-backed animated ghost (QMovie blinking GIF)
    PumpkinWidget                QLabel-backed static pumpkin (QPixmap PNG)
    OverlayWindow                timer coordinator + event-loop owner
"""

from __future__ import annotations
import time
import math
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Asset resolution — all paths are absolute so they work regardless of cwd
# ---------------------------------------------------------------------------
_ASSETS_DIR   = Path(__file__).parent.parent / "assets"
_GHOST_GIF    = _ASSETS_DIR / "ghost-kiro-blink.gif"
_PUMPKIN_PNG  = _ASSETS_DIR / "pumpkin.png"
_SCREAM_WAV   = _ASSETS_DIR / "ghost_scream.wav"
_EXORCISM_WAVS = [
        _ASSETS_DIR / "collected.wav",

    # _ASSETS_DIR / "exorcism1.wav",
    # _ASSETS_DIR / "exorcism2.wav",
]

# Overlay auto-dismiss timeout (ms)
_AUTO_DISMISS_MS = 10_000
# Animation tick interval (ms) — ~60 fps
_TICK_MS = 16

# Ghost sprite render size (GIF is 640×640; scale down to be visible but not huge)
_GHOST_W = 120
_GHOST_H = 120

# Pumpkin sprite render size
_PUMPKIN_W = 96
_PUMPKIN_H = 96

# Drag-to-exorcise snap distance in pixels (ghost centre ↔ pumpkin centre)
_EXORCISE_DIST = 100


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def _play_sound(sound_file: Path) -> None:
    """
    Play *sound_file* via pygame.mixer (non-blocking).

    Gracefully logs a warning and returns if the file is missing or
    pygame raises any exception — audio failure must never crash the CLI.
    """
    if not sound_file.exists():
        print(f"  [ghost/sound] File not found, skipping: {sound_file}", file=sys.stderr)
        return
    try:
        import pygame  # type: ignore

        if not pygame.get_init():
            pygame.init()
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        # Use Sound (not music) so multiple short clips can overlap
        snd = pygame.mixer.Sound(str(sound_file))
        snd.play()
        duration = snd.get_length()
        time.sleep(duration+0.24)  # wait for sound to finish playing
    except Exception as exc:
        print(f"  [ghost/sound] pygame error playing {sound_file.name}: {exc}",
              file=sys.stderr)


def _pick_exorcism_wav() -> Path:
    """Return a random exorcism WAV path from the available pool."""
    available = [p for p in _EXORCISM_WAVS if p.exists()]
    if not available:
        # Fall back to first entry (will trigger missing-file warning in _play_sound)
        return _EXORCISM_WAVS[0]
    return random.choice(available)


# ---------------------------------------------------------------------------
# Qt asset loaders
# ---------------------------------------------------------------------------

def _load_movie(path: Path, w: int, h: int):
    """
    Load an animated GIF as a scaled QMovie.

    Returns the QMovie (already scaled to w×h) on success, or None with a
    warning printed to stderr if the file is missing, invalid, or unreadable.
    """
    from PyQt6.QtGui import QMovie
    from PyQt6.QtCore import QSize

    if not path.exists():
        print(f"  [ghost/asset] GIF not found, using procedural fallback: {path}",
              file=sys.stderr)
        return None

    movie = QMovie(str(path))
    if not movie.isValid():
        print(f"  [ghost/asset] QMovie reports invalid GIF: {path}", file=sys.stderr)
        return None

    movie.setScaledSize(QSize(w, h))
    return movie


def _load_pixmap(path: Path, w: int, h: int):
    """
    Load a PNG/image as a scaled QPixmap.

    Returns the QPixmap on success, or None with a warning on any failure.
    """
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import Qt

    if not path.exists():
        print(f"  [ghost/asset] PNG not found, using procedural fallback: {path}",
              file=sys.stderr)
        return None

    px = QPixmap(str(path))
    if px.isNull():
        print(f"  [ghost/asset] QPixmap failed to load: {path}", file=sys.stderr)
        return None

    return px.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ---------------------------------------------------------------------------
# Procedural fallback painters (used when asset files are absent)
# ---------------------------------------------------------------------------

def _paint_fallback_ghost(w: int, h: int):
    """Return a QPixmap with a procedurally drawn purple/white ghost."""
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QPainterPath, QBrush

    canvas = QPixmap(w, h)
    canvas.fill(QColor(0, 0, 0, 0))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Head
    body = QPainterPath()
    body.addEllipse(8, 0, w - 16, h - 30)
    body.addRect(8, h // 2 - 10, w - 16, h // 2 - 10)

    # Wavy skirt
    wave = QPainterPath()
    wave.moveTo(8, h - 20)
    seg = (w - 16) / 3
    wave.quadTo(8 + seg * 0.5, h + 6,  8 + seg,       h - 20)
    wave.quadTo(8 + seg * 1.5, h + 6,  8 + seg * 2,   h - 20)
    wave.quadTo(8 + seg * 2.5, h + 6,  8 + seg * 3,   h - 20)
    wave.lineTo(8 + seg * 3, h // 2 - 10)
    wave.lineTo(8,            h // 2 - 10)
    wave.closeSubpath()

    p.setBrush(QBrush(QColor(180, 120, 255, 230)))
    p.setPen(QColor(255, 255, 255, 180))
    p.drawPath(body)
    p.drawPath(wave)

    # Eyes — white outer, dark pupil
    p.setBrush(QBrush(QColor(255, 255, 255, 255)))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawEllipse(w // 2 - 20, h // 4,     14, 18)
    p.drawEllipse(w // 2 + 6,  h // 4,     14, 18)
    p.setBrush(QBrush(QColor(40, 0, 60, 255)))
    p.drawEllipse(w // 2 - 17, h // 4 + 3,  8, 10)
    p.drawEllipse(w // 2 + 9,  h // 4 + 3,  8, 10)

    p.end()
    return canvas


def _paint_fallback_pumpkin(w: int, h: int):
    """Return a QPixmap with a procedurally drawn orange jack-o'-lantern."""
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QPainterPath, QBrush, QPen

    canvas = QPixmap(w, h)
    canvas.fill(QColor(0, 0, 0, 0))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    orange = QColor(255, 120, 0, 240)
    p.setBrush(QBrush(orange))
    p.setPen(QPen(QColor(180, 60, 0), 2))
    p.drawEllipse(10, 16, 60, 52)
    p.drawEllipse(2,  22, 36, 44)
    p.drawEllipse(42, 22, 36, 44)

    # Stem
    p.setBrush(QBrush(QColor(60, 120, 0)))
    p.setPen(QPen(QColor(40, 80, 0), 2))
    p.drawRoundedRect(34, 4, 12, 16, 3, 3)

    # Face
    p.setBrush(QBrush(QColor(20, 10, 0, 220)))
    p.setPen(QColor(0, 0, 0, 0))
    eye_l = QPainterPath()
    eye_l.moveTo(22, 32); eye_l.lineTo(30, 26); eye_l.lineTo(38, 32)
    eye_l.closeSubpath()
    eye_r = QPainterPath()
    eye_r.moveTo(42, 32); eye_r.lineTo(50, 26); eye_r.lineTo(58, 32)
    eye_r.closeSubpath()
    p.drawPath(eye_l)
    p.drawPath(eye_r)
    mouth = QPainterPath()
    mouth.moveTo(22, 46)
    mouth.cubicTo(28, 58, 52, 58, 58, 46)
    mouth.lineTo(54, 46)
    mouth.cubicTo(50, 54, 30, 54, 26, 46)
    mouth.closeSubpath()
    p.drawPath(mouth)

    p.end()
    return canvas


# ---------------------------------------------------------------------------
# GhostWidget
# ---------------------------------------------------------------------------

class GhostWidget:
    """
    Animated, draggable ghost sprite backed by a QLabel.

    If assets/ghost-kiro-blink.gif loads successfully, the GIF plays via
    QMovie (blink animation included). Otherwise a procedural purple/white
    ghost is painted via QPainter as a fallback.

    The ghost floats on a Lissajous-ish sine path. While being dragged,
    animation is paused; on mouse-release the exorcism callback fires so
    OverlayWindow can check proximity to the pumpkin.
    """

    def __init__(self, screen_rect, on_exorcised):
        from PyQt6.QtCore import Qt, QPoint
        from PyQt6.QtWidgets import QLabel

        self._on_exorcised = on_exorcised
        self._screen = screen_rect
        self._dragging = False
        self._drag_offset = QPoint(0, 0)
        self._movie = None  # holds QMovie ref to prevent GC

        # Sine-wave travel parameters
        self._tick = 0
        self._x_amplitude = (screen_rect.width()  - _GHOST_W) / 2
        self._x_center    = screen_rect.x() + screen_rect.width()  / 2 - _GHOST_W / 2
        self._y_amplitude = screen_rect.height() * 0.18
        self._y_center    = screen_rect.y() + screen_rect.height() * 0.38

        # Build the label
        self._label = QLabel()
        self._label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setFixedSize(_GHOST_W, _GHOST_H)

        # Try animated GIF first
        movie = _load_movie(_GHOST_GIF, _GHOST_W, _GHOST_H)
        if movie is not None:
            self._movie = movie          # keep a reference — QLabel doesn't own it
            self._label.setMovie(movie)
            movie.start()                # begin blinking immediately
        else:
            # Procedural fallback
            self._label.setPixmap(_paint_fallback_ghost(_GHOST_W, _GHOST_H))

        # Mouse event wiring
        self._label.mousePressEvent   = self._on_mouse_press
        self._label.mouseMoveEvent    = self._on_mouse_move
        self._label.mouseReleaseEvent = self._on_mouse_release

        sx, sy = self._pos_for_tick(0)
        self._label.move(int(sx), int(sy))
        self._label.show()

    # ── animation ──────────────────────────────────────────────────────────

    def _pos_for_tick(self, t: int) -> tuple[float, float]:
        x = self._x_center + self._x_amplitude * math.sin(t * 0.012)
        y = self._y_center  + self._y_amplitude * math.sin(t * 0.025)
        return x, y

    def tick(self) -> None:
        """Advance float animation one frame. No-op while dragging."""
        if self._dragging:
            return
        self._tick += 1
        x, y = self._pos_for_tick(self._tick)
        self._label.move(int(x), int(y))

    # ── geometry ───────────────────────────────────────────────────────────

    def center(self):
        from PyQt6.QtCore import QPoint
        pos = self._label.pos()
        return QPoint(pos.x() + _GHOST_W // 2, pos.y() + _GHOST_H // 2)

    # ── drag ───────────────────────────────────────────────────────────────

    def _on_mouse_press(self, event) -> None:
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.pos()

    def _on_mouse_move(self, event) -> None:
        from PyQt6.QtCore import Qt
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = self._label.mapToGlobal(event.pos()) - self._drag_offset
            self._label.move(new_pos)

    def _on_mouse_release(self, event) -> None:
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._on_exorcised()   # OverlayWindow checks the distance

    # ── cleanup ────────────────────────────────────────────────────────────

    def hide(self) -> None:
        if self._movie is not None:
            self._movie.stop()
        self._label.hide()


# ---------------------------------------------------------------------------
# PumpkinWidget
# ---------------------------------------------------------------------------

class PumpkinWidget:
    """
    Static pumpkin bucket anchored to the bottom-right corner of the screen.

    Renders assets/pumpkin.png via QPixmap. Falls back to a procedurally
    drawn jack-o'-lantern if the file is absent or unreadable.
    """

    def __init__(self, screen_rect):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QLabel

        self._label = QLabel()
        self._label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setFixedSize(_PUMPKIN_W, _PUMPKIN_H)

        px = _load_pixmap(_PUMPKIN_PNG, _PUMPKIN_W, _PUMPKIN_H)
        if px is not None:
            self._label.setPixmap(px)
        else:
            self._label.setPixmap(_paint_fallback_pumpkin(_PUMPKIN_W, _PUMPKIN_H))

        # Bottom-right corner with a 16 px margin
        margin = 16
        bx = screen_rect.x() + screen_rect.width()  - _PUMPKIN_W - margin
        by = screen_rect.y() + screen_rect.height() - _PUMPKIN_H - margin
        self._label.move(bx, by)
        self._label.show()

    def center(self):
        from PyQt6.QtCore import QPoint
        pos = self._label.pos()
        return QPoint(pos.x() + _PUMPKIN_W // 2, pos.y() + _PUMPKIN_H // 2)

    def hide(self) -> None:
        self._label.hide()


# ---------------------------------------------------------------------------
# OverlayWindow
# ---------------------------------------------------------------------------

class OverlayWindow:
    """
    Owns the QApplication event loop for the overlay session.

    Responsibilities:
    - Creates GhostWidget and PumpkinWidget.
    - Drives the float animation via a QTimer (~60 fps).
    - Auto-dismisses after _AUTO_DISMISS_MS milliseconds.
    - Detects exorcism (ghost dropped within _EXORCISE_DIST px of pumpkin),
      fires a random exorcism sound, then quits cleanly.
    """

    def __init__(self, on_exorcised_sound_cb):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer

        self._app = QApplication.instance() or QApplication(sys.argv)
        self._exorcism_cb = on_exorcised_sound_cb
        self._exorcised = False

        screen_rect = self._app.primaryScreen().availableGeometry()

        self._pumpkin = PumpkinWidget(screen_rect)
        self._ghost   = GhostWidget(screen_rect, self._check_exorcism)

        # ~60 fps float animation
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(_TICK_MS)
        self._anim_timer.timeout.connect(self._ghost.tick)
        self._anim_timer.start()

        # Hard auto-dismiss
        self._dismiss_timer = QTimer()
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(_AUTO_DISMISS_MS)
        self._dismiss_timer.timeout.connect(self._dismiss)
        self._dismiss_timer.start()

    # ── exorcism ───────────────────────────────────────────────────────────

    def _check_exorcism(self) -> None:
        """Called by GhostWidget on every mouse-release."""
        if self._exorcised:
            return
        gc = self._ghost.center()
        pc = self._pumpkin.center()
        dist = math.hypot(gc.x() - pc.x(), gc.y() - pc.y())
        if dist <= _EXORCISE_DIST:
            self._exorcised = True
            self._exorcism_cb()    # plays random exorcism WAV
            self._dismiss()

    # ── teardown ───────────────────────────────────────────────────────────

    def _dismiss(self) -> None:
        self._anim_timer.stop()
        self._dismiss_timer.stop()
        self._ghost.hide()
        self._pumpkin.hide()
        self._app.quit()

    def exec(self) -> None:
        """Enter the Qt event loop; returns when the overlay is dismissed."""
        self._app.exec()


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def _show_ghost_overlay() -> None:
    """
    Launch the transparent, frameless, always-on-top PyQt6 overlay:

    - Animated blinking Kiro ghost floats on a sine wave path.
    - Pumpkin bucket sits in the bottom-right corner.
    - Drag the ghost onto the pumpkin to exorcise it → plays a random
      exorcism WAV (exorcism1.wav or exorcism2.wav) and closes.
    - Auto-dismisses after 10 seconds if the user does nothing.
    """
    overlay = OverlayWindow(
        on_exorcised_sound_cb=lambda: _play_sound(_pick_exorcism_wav())
    )
    overlay.exec()


def trigger_ghost_event() -> None:
    """
    Entry point called by the CLI on non-zero exit codes.

    Plays ghost_scream.wav (non-blocking) then shows the overlay
    (blocks until dismissed or timed out).
    """
    print("\n[GHOST] A ghost has been summoned by your failure...", file=sys.stderr)
    _play_sound(_SCREAM_WAV)
    _show_ghost_overlay()
