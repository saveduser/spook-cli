"""
Ghost event system — audio + PyQt6 visual overlay.

Public API (called by cli.py):
    trigger_ghost_event(stderr_text)   orchestrates sound + overlay + AI diagnosis

Internal layout:
    _play_sound(path)            pygame audio (non-blocking, try/except wrapped)
    _show_ghost_overlay(diag)    launches the PyQt6 overlay and blocks until done
    _load_movie(path, w, h)      load animated GIF → QMovie, or None on failure
    _load_pixmap(path, w, h)     load PNG/static image → QPixmap, or None on failure
    GhostWidget                  QLabel-backed animated ghost (QMovie blinking GIF)
    PumpkinWidget                QLabel-backed static pumpkin (QPixmap PNG)
    SpeechBubbleWidget           floating speech-bubble showing the AI diagnosis
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

# Sentinel set to False permanently the first time audio init fails.
# Prevents repeated failed init attempts and noisy logs across a session.
_AUDIO_AVAILABLE: bool | None = None  # None = not yet attempted


def _ensure_audio() -> bool:
    """
    Initialise pygame.mixer on first call and cache the result.

    Returns True if the mixer is ready, False if the device is unavailable.
    Subsequent calls return the cached value instantly without re-trying.
    """
    global _AUDIO_AVAILABLE
    if _AUDIO_AVAILABLE is not None:
        return _AUDIO_AVAILABLE

    try:
        import pygame  # type: ignore

        if not pygame.get_init():
            pygame.init()

        if not pygame.mixer.get_init():
            # pre_init with safe defaults improves compatibility on headless
            # systems (ALSA dummy device, null driver, WSL, CI, etc.)
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.init()

        _AUDIO_AVAILABLE = True

    except Exception as exc:
        _AUDIO_AVAILABLE = False
        print(
            f"  [ghost/audio] Audio device unavailable — running in silent mode. ({exc})",
            file=sys.stderr,
        )

    return _AUDIO_AVAILABLE


def _play_sound(sound_file: Path) -> None:
    """
    Play *sound_file* via pygame.mixer (non-blocking, fault-tolerant).

    Fault-tolerance contract:
    - Missing file        → single debug log, returns immediately.
    - Audio device error  → logged once at mixer init time, then silent.
    - Any other exception → caught, logged, never propagated.

    The PyQt6 visual overlay continues uninterrupted regardless of audio state.
    """
    if not sound_file.exists():
        print(f"  [ghost/sound] File not found, skipping: {sound_file}", file=sys.stderr)
        return

    if not _ensure_audio():
        return  # already logged "silent mode" at init time

    try:
        import pygame  # type: ignore

        snd = pygame.mixer.Sound(str(sound_file))
        snd.play()
        duration = snd.get_length()
    except Exception as exc:
        print(
            f"  [ghost/sound] Playback error for {sound_file.name}: {exc}",
            file=sys.stderr,
        )
        return

    # Sleep outside the try block — the sound is already submitted to the
    # mixer; even if this sleep is interrupted the clip will still play out.
    time.sleep(duration + 0.24)


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
    Animated, draggable ghost sprite backed by a QLabel, with a live
    taunting whisper label positioned directly above the sprite.

    The whisper label is a sibling top-level window that mirrors every move
    of the sprite so the two always travel together — during float animation
    and during drag.

    If assets/ghost-kiro-blink.gif loads successfully, the GIF plays via
    QMovie (blink animation included). Otherwise a procedural purple/white
    ghost is painted via QPainter as a fallback.

    The ghost floats on a Lissajous-ish sine path. While being dragged,
    animation is paused; on mouse-release the exorcism callback fires so
    OverlayWindow can check proximity to the pumpkin.
    """

    # Gap between the bottom of the whisper label and the top of the sprite
    _WHISPER_GAP   = 6
    # Maximum pixel width for the whisper label
    _WHISPER_MAX_W = 380
    # Minimum pixel width (so the label doesn't collapse on short strings)
    _WHISPER_MIN_W = 180

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

        # ── sprite label ────────────────────────────────────────────────
        self._label = QLabel()
        _overlay_flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._label.setWindowFlags(_overlay_flags)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setFixedSize(_GHOST_W, _GHOST_H)

        # Try animated GIF first
        movie = _load_movie(_GHOST_GIF, _GHOST_W, _GHOST_H)
        if movie is not None:
            self._movie = movie
            self._label.setMovie(movie)
            movie.start()
        else:
            self._label.setPixmap(_paint_fallback_ghost(_GHOST_W, _GHOST_H))

        # ── whisper label ───────────────────────────────────────────────
        # Styled with the Soft Tech-Wear palette:
        #   background transparent, text #E2E8F0, border 1px solid #00F2FE,
        #   5 px padding, 6 px rounded corners.
        self._whisper = QLabel("")
        self._whisper.setWindowFlags(_overlay_flags)
        self._whisper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._whisper.setWordWrap(True)
        self._whisper.setMaximumWidth(self._WHISPER_MAX_W)
        self._whisper.setMinimumWidth(self._WHISPER_MIN_W)
        self._whisper.setStyleSheet(
            "QLabel {"
            "  background-color: transparent;"
            "  color: #E2E8F0;"
            "  border: 1px solid #00F2FE;"
            "  border-radius: 6px;"
            "  padding: 5px;"
            "  font-size: 11px;"
            "  font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;"
            "}"
        )
        self._whisper.show()

        # Mouse event wiring on the sprite (drag moves both labels)
        self._label.mousePressEvent   = self._on_mouse_press
        self._label.mouseMoveEvent    = self._on_mouse_move
        self._label.mouseReleaseEvent = self._on_mouse_release

        sx, sy = self._pos_for_tick(0)
        self._label.move(int(sx), int(sy))
        self._label.show()
        self._reposition_whisper()  # initial whisper placement

    # ── whisper text & positioning ─────────────────────────────────────

    def update_whisper(self, text: str) -> None:
        """Update the taunting whisper text displayed above the sprite."""
        self._whisper.setText(text)
        self._whisper.adjustSize()
        self._reposition_whisper()

    def _reposition_whisper(self) -> None:
        """
        Place the whisper label centred above the sprite label.

        The whisper label is a separate top-level window; we position it
        relative to the sprite's current screen position so the two always
        appear connected.
        """
        sprite_pos = self._label.pos()
        sprite_cx  = sprite_pos.x() + _GHOST_W // 2
        wh_w = self._whisper.width()
        wh_h = self._whisper.height()
        wx = sprite_cx - wh_w // 2
        wy = sprite_pos.y() - wh_h - self._WHISPER_GAP
        self._whisper.move(wx, wy)

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
        self._reposition_whisper()

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
            self._reposition_whisper()  # keep whisper locked to sprite

    def _on_mouse_release(self, event) -> None:
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._on_exorcised()   # OverlayWindow checks the distance

    # ── cleanup ────────────────────────────────────────────────────────────

    def hide(self) -> None:
        if self._movie is not None:
            self._movie.stop()
        self._whisper.hide()
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
# SpeechBubbleWidget
# ---------------------------------------------------------------------------

# Maximum characters per line in the bubble
_BUBBLE_MAX_LINE = 48
# Width of the bubble window in pixels
_BUBBLE_W = 340
# Vertical offset above the ghost sprite
_BUBBLE_OFFSET_Y = 20


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap *text* to lines of at most *max_chars* characters, on word boundaries."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class SpeechBubbleWidget:
    """
    Frameless, transparent speech bubble that floats above the ghost.

    Renders a rounded-rectangle chat bubble with a tail pointing downward
    toward the ghost, containing the AI-generated diagnosis text.
    Tracks the ghost position every tick so it stays anchored above it.
    """

    # Padding inside the bubble
    _PAD_X = 14
    _PAD_Y = 10
    # Corner radius of the rounded rect
    _RADIUS = 14
    # Height of the triangular tail
    _TAIL_H = 12
    # Width of the tail at its base
    _TAIL_W = 18
    # Font size
    _FONT_PT = 11

    def __init__(self, text: str):
        from PyQt6.QtCore import Qt, QPoint
        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtGui import QFont, QFontMetrics

        self._lines = _wrap_text(text, _BUBBLE_MAX_LINE)

        # Measure text to size the bubble
        font = QFont("Segoe UI", self._FONT_PT) if sys.platform == "win32" \
               else QFont("Helvetica Neue", self._FONT_PT)
        fm = QFontMetrics(font)
        line_h   = fm.height()
        max_w    = max((fm.horizontalAdvance(ln) for ln in self._lines), default=80)
        text_w   = max_w
        text_h   = line_h * len(self._lines)

        self._w = text_w + self._PAD_X * 2
        self._h = text_h + self._PAD_Y * 2 + self._TAIL_H

        self._label = QLabel()
        self._label.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._label.setFixedSize(self._w, self._h)

        # Pre-render the bubble onto a pixmap (static — text never changes)
        self._label.setPixmap(self._render(font, fm, line_h))
        self._label.show()

    def _render(self, font, fm, line_h):
        from PyQt6.QtGui import (
            QPixmap, QPainter, QColor, QPainterPath, QBrush, QPen, QFont
        )

        canvas = QPixmap(self._w, self._h)
        canvas.fill(QColor(0, 0, 0, 0))
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        bubble_h = self._h - self._TAIL_H

        # Bubble body
        path = QPainterPath()
        path.addRoundedRect(0, 0, self._w, bubble_h, self._RADIUS, self._RADIUS)

        # Downward-pointing tail centred at the bottom
        tail_cx = self._w // 2
        tail = QPainterPath()
        tail.moveTo(tail_cx - self._TAIL_W // 2, bubble_h)
        tail.lineTo(tail_cx,                      self._h)
        tail.lineTo(tail_cx + self._TAIL_W // 2,  bubble_h)
        tail.closeSubpath()
        path = path.united(tail)

        # Shadow / border
        p.setPen(QPen(QColor(80, 0, 120, 180), 2))
        p.setBrush(QBrush(QColor(28, 8, 48, 220)))  # dark purple, semi-transparent
        p.drawPath(path)

        # Ghost-green accent line at top
        p.setPen(QPen(QColor(140, 255, 180, 200), 2))
        p.setBrush(QBrush(QColor(0, 0, 0, 0)))
        p.drawRoundedRect(2, 2, self._w - 4, 4, 2, 2)

        # Text
        p.setFont(font)
        p.setPen(QColor(220, 255, 210))  # pale mint
        for i, line in enumerate(self._lines):
            y = self._PAD_Y + i * line_h + fm.ascent()
            p.drawText(self._PAD_X, y, line)

        p.end()
        return canvas

    def move_above(self, ghost_center_x: int, ghost_top_y: int) -> None:
        """Reposition the bubble so its tail points at the ghost's top edge."""
        x = ghost_center_x - self._w // 2
        y = ghost_top_y - self._h - _BUBBLE_OFFSET_Y
        self._label.move(x, y)

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

    def __init__(self, on_exorcised_sound_cb, diagnosis: str = ""):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        from spookcli.whispers import start_whispers, get_current_whispers

        self._app = QApplication.instance() or QApplication(sys.argv)
        self._exorcism_cb = on_exorcised_sound_cb
        self._exorcised = False
        self._get_whisper = get_current_whispers  # stored to avoid repeated import

        screen_rect = self._app.primaryScreen().availableGeometry()

        self._pumpkin = PumpkinWidget(screen_rect)
        self._ghost   = GhostWidget(screen_rect, self._check_exorcism)

        # Speech bubble — shown only when there's a diagnosis
        self._bubble: SpeechBubbleWidget | None = None
        if diagnosis.strip():
            self._bubble = SpeechBubbleWidget(diagnosis)
            self._update_bubble()   # initial position

        # Start the OS anomaly poller (daemon thread, non-blocking)
        start_whispers()
        # Seed the whisper label immediately with whatever is available
        self._ghost.update_whisper(get_current_whispers())

        # ~60 fps float animation
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(_TICK_MS)
        self._anim_timer.timeout.connect(self._on_tick)
        self._anim_timer.start()

        # Whisper rotation — fires every 3 seconds to cycle through OS taunts
        self._whisper_timer = QTimer()
        self._whisper_timer.setInterval(3_000)
        self._whisper_timer.timeout.connect(self._on_whisper_tick)
        self._whisper_timer.start()

        # Hard auto-dismiss
        self._dismiss_timer = QTimer()
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(_AUTO_DISMISS_MS)
        self._dismiss_timer.timeout.connect(self._dismiss)
        self._dismiss_timer.start()

    # ── per-frame logic ────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._ghost.tick()
        self._update_bubble()

    def _on_whisper_tick(self) -> None:
        """
        Fired every 3 seconds by the whisper timer.

        Calls get_current_whispers() — which returns instantly from the
        daemon thread's cache — and pushes the result to the ghost label.
        """
        self._ghost.update_whisper(self._get_whisper())

    def _update_bubble(self) -> None:
        """Keep the speech bubble centred above the ghost's current position."""
        if self._bubble is None:
            return
        gc = self._ghost.center()
        ghost_top_y = self._ghost._label.pos().y()
        self._bubble.move_above(gc.x(), ghost_top_y)

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
        self._whisper_timer.stop()
        self._dismiss_timer.stop()
        if self._bubble is not None:
            self._bubble.hide()
        self._ghost.hide()
        self._pumpkin.hide()
        self._app.quit()

    def exec(self) -> None:
        """Enter the Qt event loop; returns when the overlay is dismissed."""
        self._app.exec()


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def _show_ghost_overlay(diagnosis: str = "") -> None:
    """
    Launch the transparent, frameless, always-on-top PyQt6 overlay:

    - Animated blinking Kiro ghost floats on a sine wave path.
    - Speech bubble above the ghost displays the AI error diagnosis.
    - Pumpkin bucket sits in the bottom-right corner.
    - Drag the ghost onto the pumpkin to exorcise it → plays a random
      exorcism WAV (exorcism1.wav or exorcism2.wav) and closes.
    - Auto-dismisses after 10 seconds if the user does nothing.
    """
    overlay = OverlayWindow(
        on_exorcised_sound_cb=lambda: _play_sound(_pick_exorcism_wav()),
        diagnosis=diagnosis,
    )
    overlay.exec()


def trigger_ghost_event(stderr_text: str = "") -> None:
    """
    Entry point called by the CLI on non-zero exit codes.

    Fetches a spooky AI diagnosis of *stderr_text*, plays ghost_scream.wav,
    then shows the overlay (blocks until dismissed or timed out).
    """
    from spookcli.ai import get_spooky_diagnosis
    from spookcli.board import record_failure

    print("\n[GHOST] A ghost has been summoned by your failure...", file=sys.stderr)

    # Persist stats for the BBS board before anything visual happens
    record_failure(stderr_text)

    # Fetch diagnosis before opening overlay (fast: 1.5 s Ollama timeout or instant fallback)
    diagnosis = get_spooky_diagnosis(stderr_text)
    print(f"[GHOST] {diagnosis}", file=sys.stderr)

    _play_sound(_SCREAM_WAV)
    _show_ghost_overlay(diagnosis=diagnosis)
