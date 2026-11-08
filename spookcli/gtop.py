"""
spookcli/gtop.py — gtop: Haunted Process Monitor.

A frameless, glassmorphic PyQt6 desktop process monitor built from the
left-hand panel of the "gtop - Audio & Interaction Blueprint Edition"
Stitch design.  The developer HUD on the right side is intentionally not
implemented.

The window is translucent, drags by its header, and streams live psutil
telemetry into a haunted process table, CPU/RAM gauges, a taunting Kiro
mascot, a candy bucket, and a crypt for slain processes.
"""

from __future__ import annotations

import contextlib
import math
import os
import random
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import psutil
from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QMovie,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

C_VOID = "#0B0813"
C_BASE = "#120B1D"
C_PANEL = "#0E0918"
C_BORDER = "#38254A"
C_TRACK = "#201431"
C_TEXT = "#F1F5F9"
C_DIM = "#A89CB9"
C_ORANGE = "#FF7A00"
C_GREEN = "#39FF14"
C_PURPLE = "#BD00FF"
C_ICY = "#7DE9FF"

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

REFRESH_SECS = 2.0
WHISPER_SECS = 4.0
CPU_SPIKE = 50.0
MEM_SPIKE = 40.0
MAX_PROCS = 25

# Ports whose current holders are treated as squatters / port hauntings.
HAUNTED_PORTS: dict[int, str] = {
    8080: "web",
    3000: "dev",
    5432: "postgres",
    8000: "http",
    5173: "vite",
    3306: "mysql",
    6379: "redis",
}

LEAK_WINDOW = 8
LEAK_GROWTH_MB = 12.0
LEAK_FALLBACK_MB = 250.0
TRACE_MAX_ROWS = 80

_TAUNTS = {
    "ram": [
        '"Trick or Treat! {name} is devouring {mem:.0f}% of your candy souls."',
        '"{name} is feasting on the soul pool. I approve."',
        '"All that RAM and still nothing compiles, mortal."',
    ],
    "cpu": [
        '"The cores are ablaze! {name} is feasting on {cpu:.0f}% of your heat."',
        '"{name} has ascended beyond your thermal limits."',
        '"Warmth. {name} gives me warmth."',
    ],
    "zombie": [
        '"A restless spirit roams your process table. PID {pid} refuses to die."',
        '"The dead do not rest here. PID {pid} joins the haunt."',
    ],
    "idle": [
        '"The system is eerily quiet… suspicious. Something is hiding."',
        '"No spikes. The poltergeists are planning something."',
        '"Enjoy the silence. It will not last."',
    ],
}

_POKE_QUOTES = [
    ("RAM GLUTTON DETECTED", '"Trick or Treat! Chrome is devouring 5GB of candy souls. Don\'t close those cursed tabs!"', "FEASTING", C_GREEN),
    ("WITCHING HOUR", '"The veil is thin. Your CPU is thinner."', "WATCHFUL", C_PURPLE),
    ("CORE HEAT RISING", '"Every process is a candle. Your machine is a bonfire."', "BURNING", C_ORANGE),
    ("SOULS IN PURGATORY", '"The crypt is never truly empty, mortal."', "LINGERING", C_PURPLE),
]


def _load_ghost_movie(size: QSize) -> QMovie | None:
    for asset_name in ("blinking_ghost.gif", "ghost-kiro-blink.gif"):
        movie = QMovie(str(ASSETS_DIR / asset_name))
        if movie.isValid():
            movie.setScaledSize(size)
            return movie
    return None


def _style(template: str) -> str:
    return (
        template.replace("@VOID@", C_VOID)
        .replace("@BASE@", C_BASE)
        .replace("@PANEL@", C_PANEL)
        .replace("@BORDER@", C_BORDER)
        .replace("@TRACK@", C_TRACK)
        .replace("@TEXT@", C_TEXT)
        .replace("@DIM@", C_DIM)
        .replace("@ORANGE@", C_ORANGE)
        .replace("@GREEN@", C_GREEN)
        .replace("@PURPLE@", C_PURPLE)
        .replace("@ICY@", C_ICY)
    )


def _label(text: str, color: str = C_TEXT, size: int = 11, bold: bool = False, italic: bool = False) -> QLabel:
    label = QLabel(text)
    weight = "700" if bold else "400"
    slant = "italic" if italic else "normal"
    label.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: {weight}; font-style: {slant}; background: transparent;")
    return label


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


@dataclass
class ProcessRow:
    pid: int
    name: str
    cpu: float
    mem: float
    status: str
    ppid: int = 0
    rss_mb: float = 0.0
    num_threads: int = 1
    ports: list[int] = field(default_factory=list)
    leak: bool = False

    @property
    def haunted_ports(self) -> list[int]:
        return [port for port in self.ports if port in HAUNTED_PORTS]

    @property
    def squatter(self) -> bool:
        return bool(self.haunted_ports)


@dataclass
class SystemSnapshot:
    cpu_total: float = 0.0
    mem_percent: float = 0.0
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0
    core_count: int = 0
    processes: list[ProcessRow] = field(default_factory=list)
    all_processes: list[ProcessRow] = field(default_factory=list)
    top_cpu: ProcessRow | None = None
    top_mem: ProcessRow | None = None
    zombie_pids: list[int] = field(default_factory=list)
    leak_pid: int | None = None
    leak_growth: float = 0.0
    squatter_count: int = 0


@dataclass
class CryptEntry:
    pid: int
    name: str
    signal: str


def _listening_ports() -> dict[int, list[int]]:
    """Map PID -> sorted listening TCP ports. Degrades to {} when denied."""
    mapping: dict[int, set[int]] = {}
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return {}
    except Exception:
        return {}

    for connection in connections:
        try:
            if connection.status != psutil.CONN_LISTEN or connection.pid is None:
                continue
            if connection.laddr is None:
                continue
            port = int(connection.laddr.port)
            mapping.setdefault(int(connection.pid), set()).add(port)
        except Exception:
            continue

    return {pid: sorted(ports) for pid, ports in mapping.items()}


def _update_rss_history(
    rows: list[ProcessRow], history: dict[int, deque[float]]
) -> None:
    alive = {row.pid for row in rows}
    for pid in [pid for pid in history if pid not in alive]:
        history.pop(pid, None)
    for row in rows:
        history.setdefault(row.pid, deque(maxlen=LEAK_WINDOW)).append(row.rss_mb)


def _detect_leak(
    rows: list[ProcessRow], history: dict[int, deque[float]]
) -> tuple[int | None, float]:
    """Prefer a process whose RSS is steadily climbing, else the biggest hog."""
    best_growth = 0.0
    best_pid: int | None = None

    own_pid = os.getpid()
    for row in rows:
        if row.pid == own_pid:
            continue
        samples = history.get(row.pid)
        if not samples or len(samples) < 3:
            continue
        growth = samples[-1] - samples[0]
        if growth >= LEAK_GROWTH_MB and samples[-1] >= samples[0] - 1.0:
            if growth > best_growth:
                best_growth = growth
                best_pid = row.pid

    if best_pid is not None:
        return best_pid, best_growth

    candidates = [
        row
        for row in rows
        if row.pid != own_pid and row.rss_mb >= LEAK_FALLBACK_MB
    ]
    if candidates:
        biggest = max(candidates, key=lambda row: row.rss_mb)
        return biggest.pid, 0.0
    return None, 0.0


def _collect_snapshot(
    rss_history: dict[int, deque[float]] | None = None,
) -> SystemSnapshot:
    snapshot = SystemSnapshot()

    try:
        snapshot.cpu_total = float(psutil.cpu_percent(interval=None))
    except Exception:
        pass

    try:
        memory = psutil.virtual_memory()
        snapshot.mem_percent = float(memory.percent)
        snapshot.mem_total_gb = memory.total / 1_000_000_000
        snapshot.mem_used_gb = (memory.total - memory.available) / 1_000_000_000
    except Exception:
        pass

    try:
        snapshot.core_count = psutil.cpu_count(logical=True) or 0
    except Exception:
        pass

    rows: list[ProcessRow] = []
    try:
        iterator = psutil.process_iter(
            [
                "pid",
                "name",
                "cpu_percent",
                "memory_percent",
                "status",
                "ppid",
                "num_threads",
                "memory_info",
            ]
        )
        for proc in iterator:
            try:
                info = proc.info
                memory_info = info.get("memory_info")
                rss_mb = (
                    float(getattr(memory_info, "rss", 0) or 0) / (1024 * 1024)
                    if memory_info is not None
                    else 0.0
                )
                rows.append(
                    ProcessRow(
                        pid=int(info.get("pid") or 0),
                        name=(info.get("name") or "?")[:28],
                        cpu=round(float(info.get("cpu_percent") or 0.0), 1),
                        mem=round(float(info.get("memory_percent") or 0.0), 1),
                        status=str(info.get("status") or ""),
                        ppid=int(info.get("ppid") or 0),
                        rss_mb=round(rss_mb, 1),
                        num_threads=int(info.get("num_threads") or 1),
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
            except Exception:
                pass
    except Exception:
        pass

    port_map = _listening_ports()
    for row in rows:
        ports = port_map.get(row.pid)
        if ports:
            row.ports = ports

    if rss_history is not None:
        _update_rss_history(rows, rss_history)
        snapshot.leak_pid, snapshot.leak_growth = _detect_leak(
            rows, rss_history
        )
        for row in rows:
            row.leak = row.pid == snapshot.leak_pid

    # Port squatters first, then suspected leaks, then the usual CPU/memory race.
    rows.sort(
        key=lambda row: (
            0 if row.squatter else 1,
            0 if row.leak else 1,
            -row.cpu,
            -row.mem,
        )
    )
    snapshot.all_processes = rows
    snapshot.processes = rows[:MAX_PROCS]
    snapshot.squatter_count = sum(1 for row in rows if row.squatter)

    if rows:
        snapshot.top_cpu = max(rows, key=lambda row: row.cpu)
        snapshot.top_mem = max(rows, key=lambda row: row.mem)

    snapshot.zombie_pids = [
        row.pid for row in rows if row.status == psutil.STATUS_ZOMBIE
    ]
    return snapshot


class SnapshotWorker(QThread):
    snapshot_ready = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._rss_history: dict[int, deque[float]] = {}

    def run(self) -> None:
        try:
            for proc in psutil.process_iter(["pid"]):
                try:
                    proc.cpu_percent(None)
                except Exception:
                    pass
        except Exception:
            pass

        self._stop_event.wait(0.4)

        while not self._stop_event.is_set():
            try:
                snap = _collect_snapshot(self._rss_history)
            except Exception:
                snap = SystemSnapshot()
            self.snapshot_ready.emit(snap)
            self._stop_event.wait(REFRESH_SECS)

    def stop(self) -> None:
        self._stop_event.set()
        self.wait(3000)


class AudioEngine:
    def __init__(self) -> None:
        self.muted = False
        self._ready: bool | None = None
        self._driver = ""
        self.last_error = ""
        self._sounds: dict[str, object] = {}

    @property
    def available(self) -> bool:
        return self._ensure_audio()

    @property
    def driver(self) -> str:
        return self._driver

    @contextlib.contextmanager
    def _quiet_native_stderr(self):
        if not sys.platform.startswith("linux"):
            yield
            return
        saved = devnull = None
        try:
            saved = os.dup(2)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
        except OSError:
            if saved is not None:
                os.close(saved)
            if devnull is not None:
                os.close(devnull)
            yield
            return
        try:
            yield
        finally:
            os.dup2(saved, 2)
            os.close(saved)
            os.close(devnull)

    def _ensure_audio(self) -> bool:
        if self._ready is not None:
            return self._ready
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
        except Exception as exc:
            self.last_error = str(exc)
            self._ready = False
            return False

        if pygame.mixer.get_init():
            self._ready = True
            self._driver = "default"
            return True

        explicit = os.environ.get("SDL_AUDIODRIVER", "").strip()
        if explicit:
            candidates = [explicit]
        elif sys.platform.startswith("linux"):
            candidates = ["pulseaudio", "pipewire", "alsa"]
        else:
            candidates = [""]

        for driver in candidates:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            if driver:
                os.environ["SDL_AUDIODRIVER"] = driver
            else:
                os.environ.pop("SDL_AUDIODRIVER", None)
            try:
                with self._quiet_native_stderr():
                    pygame.mixer.pre_init(44100, -16, 2, 512)
                    pygame.mixer.init()
                self._ready = True
                self._driver = driver or "default"
                self.last_error = ""
                return True
            except Exception as exc:
                self.last_error = f"{driver or 'default'}: {exc}"

        self._ready = False
        return False

    def play(self, name: str, volume: float = 0.55) -> None:
        if self.muted:
            return
        path = ASSETS_DIR / name
        if not path.exists() or not self._ensure_audio():
            return
        try:
            import pygame

            sound = self._sounds.get(name)
            if sound is None:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(volume)
                self._sounds[name] = sound
            sound.play()
        except Exception:
            pass
    def play_loop(self, name: str, volume: float = 0.55) -> None:
        if self.muted:
            return
        path = ASSETS_DIR / name
        if not path.exists() or not self._ensure_audio():
            return
        try:
            import pygame

            sound = self._sounds.get(name)
            if sound is None:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(volume)
                self._sounds[name] = sound
            
            # The loops=-1 argument tells pygame to repeat the sound indefinitely
            sound.play(loops=-1)
        except Exception:
            pass

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        if muted:
            try:
                import pygame

                pygame.mixer.stop()
            except Exception:
                pass


class PulseDot(QWidget):
    def __init__(self, color: str = C_ORANGE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._phase = 0.0
        self.setFixedSize(14, 14)
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(50)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.16) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QRectF(self.rect()).center()
        pulse = 0.5 + 0.5 * math.sin(self._phase)

        glow = QColor(self._color)
        glow.setAlpha(int(55 + 70 * pulse))
        gradient = QRadialGradient(center, 7.0)
        gradient.setColorAt(0.0, glow)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, 7.0, 7.0)

        core = QColor(self._color)
        painter.setBrush(core)
        painter.drawEllipse(center, 3.1 + pulse * 0.5, 3.1 + pulse * 0.5)


class AudioBars(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self._active = True
        self.setFixedSize(18, 14)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(90)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def _tick(self) -> None:
        if self._active:
            self._phase = (self._phase + 0.36) % (math.pi * 2)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        colors = [QColor(C_GREEN), QColor(C_PURPLE), QColor(C_ORANGE)]
        for index, color in enumerate(colors):
            if self._active:
                wave = 0.5 + 0.5 * math.sin(self._phase + index * 1.9)
            else:
                wave = 0.15
            bar_height = 4.0 + wave * 9.0
            x = 1.5 + index * 5.6
            rect = QRectF(x, 13.0 - bar_height, 2.6, bar_height)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 1.3, 1.3)


class AudioToggle(QFrame):
    muted_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._muted = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setToolTip("Toggle spectral audio engine")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)
        self._icon = _label("🔊", C_PURPLE, 10, bold=True)
        self._bars = AudioBars()
        layout.addWidget(self._icon)
        layout.addWidget(self._bars)
        self._apply_style()

    def _apply_style(self) -> None:
        border = C_PURPLE if not self._muted else C_BORDER
        self.setStyleSheet(
            _style(
                "AudioToggle {"
                " background: @BASE@;"
                " border: 1px solid @EDGE@;"
                " border-radius: 6px;"
                "}"
            ).replace("@EDGE@", border)
        )

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._icon.setText("🔇" if muted else "🔊")
        self._icon.setStyleSheet(
            f"color: {C_DIM if muted else C_PURPLE}; font-size: 10px; background: transparent;"
        )
        self._bars.set_active(not muted)
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_muted(not self._muted)
            self.muted_changed.emit(self._muted)
        super().mousePressEvent(event)


class DecorOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 14.0, 14.0)
        painter.setClipPath(clip)

        painter.setPen(QPen(QColor(255, 255, 255, 7), 1))
        for y in range(0, self.height(), 3):
            painter.drawLine(0, y, self.width(), y)

        self._web(painter, 0, 0, 1, 1)
        self._web(painter, self.width(), 0, -1, 1)

    def _web(self, painter: QPainter, x: int, y: int, sx: int, sy: int) -> None:
        painter.save()
        painter.translate(x, y)
        painter.scale(sx, sy)
        painter.setPen(QPen(QColor(168, 156, 185, 65), 1.0))
        for degrees in (2, 20, 38, 56, 74, 88):
            radians = math.radians(degrees)
            painter.drawLine(
                QPoint(0, 0),
                QPoint(int(48 * math.cos(radians)), int(48 * math.sin(radians))),
            )
        for radius in (16, 30, 46):
            path = QPainterPath()
            path.moveTo(radius, 0)
            path.arcTo(QRectF(-radius, -radius, radius * 2, radius * 2), 0, -90)
            painter.drawPath(path)
        painter.restore()


class GlowBar(QWidget):
    def __init__(self, colors: tuple[str, str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._colors = colors
        self.setFixedHeight(9)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, float(value)))
        self.update()

    value = pyqtProperty(float, fget=_get_value, fset=_set_value)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        track = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QColor(C_TRACK))
        painter.drawRoundedRect(track, 2.5, 2.5)

        fill_width = self.width() * (self._value / 100.0)
        if fill_width <= 2:
            return

        accent = QColor(self._colors[1])
        glow = QColor(accent)
        glow.setAlpha(60)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(0, -1, fill_width, self.height() + 2), 3.5, 3.5)

        gradient = QLinearGradient(0, 0, fill_width, 0)
        gradient.setColorAt(0.0, QColor(self._colors[0]))
        gradient.setColorAt(0.55, QColor(self._colors[1]))
        gradient.setColorAt(1.0, QColor(self._colors[2]))
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(0, 0, fill_width, self.height()), 2.5, 2.5)


class GaugeCard(QFrame):
    def __init__(
        self,
        icon: str,
        title: str,
        accent: str,
        colors: tuple[str, str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent
        self._animation: QPropertyAnimation | None = None
        self.setStyleSheet(
            _style(
                "GaugeCard {"
                " background: rgba(18, 11, 29, 205);"
                " border: 1px solid @BORDER@;"
                " border-radius: 7px;"
                "}"
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self._title = _label(f"{icon} {title}", accent, 10, bold=True)
        self._value = _label("0.0%", C_TEXT, 10, bold=True)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._title)
        top.addStretch(1)
        top.addWidget(self._value)

        self._bar = GlowBar(colors)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)
        self._note = _label("SCANNING", C_DIM, 8)
        self._status = _label("", accent, 8, bold=True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self._note)
        bottom.addStretch(1)
        bottom.addWidget(self._status)

        layout.addLayout(top)
        layout.addWidget(self._bar)
        layout.addLayout(bottom)

    def set_metrics(self, value: float, value_text: str, note: str, status: str) -> None:
        self._value.setText(value_text)
        self._note.setText(note)
        self._status.setText(status)
        target = max(0.0, min(100.0, value))
        if self._animation is not None:
            self._animation.stop()
        self._animation = QPropertyAnimation(self._bar, b"value", self)
        self._animation.setDuration(520)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self._bar.value)
        self._animation.setEndValue(target)
        self._animation.start()


class HeaderBar(QFrame):
    minimize_requested = pyqtSignal()
    close_requested = pyqtSignal()
    spook_requested = pyqtSignal()
    audio_muted = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self.setFixedHeight(46)
        self.setStyleSheet(
            _style(
                "HeaderBar {"
                " background: rgba(11, 8, 19, 225);"
                " border-bottom: 1px solid @BORDER@;"
                " border-top-left-radius: 14px;"
                " border-top-right-radius: 14px;"
                "}"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(7)

        layout.addWidget(PulseDot(C_ORANGE))

        brand = _label("GTOP", C_ORANGE, 12, bold=True)
        brand.setStyleSheet(
            f"color: {C_ORANGE}; font-size: 12px; font-weight: 800; letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(brand)

        badge = QLabel("🎃 ALL HALLOWS' EVE")
        badge.setStyleSheet(
            _style(
                "color: @PURPLE@;"
                " font-size: 8px;"
                " font-weight: 700;"
                " background: rgba(189, 0, 255, 38);"
                " border: 1px solid rgba(189, 0, 255, 120);"
                " border-radius: 4px;"
                " padding: 2px 6px;"
            )
        )
        layout.addWidget(badge)
        layout.addStretch(1)

        self._cpu = _label("89%", C_TEXT, 9, bold=True)
        self._ram = _label("82%", C_TEXT, 9, bold=True)
        layout.addWidget(_label("CPU", C_ORANGE, 9, bold=True))
        layout.addWidget(self._cpu)
        layout.addWidget(_label("|", C_BORDER, 9))
        layout.addWidget(_label("RAM", C_GREEN, 9, bold=True))
        layout.addWidget(self._ram)

        self.audio_toggle = AudioToggle()
        self.audio_toggle.muted_changed.connect(self.audio_muted.emit)
        layout.addWidget(self.audio_toggle)

        minimize = self._window_dot(C_DIM, "Minimize gtop")
        minimize.clicked.connect(self.minimize_requested.emit)
        spook = self._window_dot(C_PURPLE, "Summon a ghost swarm")
        spook.clicked.connect(self.spook_requested.emit)
        close = self._window_dot(C_ORANGE, "Banish gtop")
        close.clicked.connect(self.close_requested.emit)
        layout.addWidget(minimize)
        layout.addWidget(spook)
        layout.addWidget(close)

    def _window_dot(self, color: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(11, 11)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setStyleSheet(
            f"QPushButton {{ background: {color}; border: none; border-radius: 5px; }}"
            f"QPushButton:hover {{ background: {C_TEXT}; }}"
        )
        return button

    def set_metrics(self, cpu: float, ram: float) -> None:
        self._cpu.setText(f"{cpu:.0f}%")
        self._ram.setText(f"{ram:.0f}%")

    def set_muted(self, muted: bool) -> None:
        self.audio_toggle.set_muted(muted)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(
                event.globalPosition().toPoint() - self._drag_offset
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class CandyBanner(QFrame):
    spook_requested = pyqtSignal()
    bucket_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = 666
        self._is_contained = False
        self._shake_animation: QPropertyAnimation | None = None
        self.setFixedHeight(58)
        self.setStyleSheet(
            _style(
                "CandyBanner {"
                " background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                " stop:0 rgba(23, 11, 38, 235),"
                " stop:0.5 rgba(38, 19, 11, 235),"
                " stop:1 rgba(23, 11, 38, 235));"
                " border-bottom: 1px solid @BORDER@;"
                "}"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 12, 8)
        layout.setSpacing(10)

        self._pumpkin = ClickableLabel()
        self._pumpkin.setFixedSize(36, 36)
        self._pumpkin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pumpkin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pumpkin.setToolTip("Jack-o'-lantern soul bucket")
        pixmap = QPixmap(str(ASSETS_DIR / "pumpkin.png"))
        if not pixmap.isNull():
            self._pumpkin.setPixmap(
                pixmap.scaled(
                    34,
                    34,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._pumpkin.setText("🎃")
            self._pumpkin.setStyleSheet("font-size: 24px; background: transparent;")
        self._pumpkin.clicked.connect(self.bucket_clicked.emit)
        layout.addWidget(self._pumpkin)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        title = _label("🎃 SOUL CANDY BUCKET", C_ORANGE, 9, bold=True)
        title.setStyleSheet(
            f"color: {C_ORANGE}; font-size: 9px; font-weight: 800; letter-spacing: 1px; background: transparent;"
        )
        ready = QLabel("HARVEST READY")
        ready.setStyleSheet(
            _style(
                "color: @GREEN@;"
                " font-size: 8px;"
                " font-weight: 700;"
                " background: rgba(57, 255, 20, 32);"
                " border: 1px solid rgba(57, 255, 20, 105);"
                " border-radius: 3px;"
                " padding: 1px 4px;"
            )
        )
        top_row.addWidget(title)
        top_row.addWidget(ready)
        top_row.addStretch(1)

        self._count_label = QLabel()
        self._count_label.setTextFormat(Qt.TextFormat.RichText)
        self._count_label.setStyleSheet("background: transparent;")
        self._refresh_count()

        text_column.addLayout(top_row)
        text_column.addWidget(self._count_label)
        layout.addLayout(text_column)
        layout.addStretch(1)

        boo = QPushButton("👻 BOO!")
        boo.setCursor(Qt.CursorShape.PointingHandCursor)
        boo.setFixedHeight(26)
        boo.setStyleSheet(
            _style(
                "QPushButton {"
                " color: @PURPLE@;"
                " background: rgba(189, 0, 255, 32);"
                " border: 1px solid rgba(189, 0, 255, 120);"
                " border-radius: 5px;"
                " font-size: 9px;"
                " font-weight: 700;"
                " padding: 0 8px;"
                "}"
                "QPushButton:hover {"
                " color: @VOID@;"
                " background: @PURPLE@;"
                "}"
            )
        )
        boo.clicked.connect(self.spook_requested.emit)
        layout.addWidget(boo)

    @property
    def pumpkin_label(self) -> QLabel:
        return self._pumpkin

    def set_contained(self, contained: bool = True) -> None:
        self._is_contained = contained
        if contained:
            self._count_label.setText(
                f"<span style='color:{C_DIM};font-size:8px;font-family:monospace;'>"
                f"TREATS COLLECTED: "
                f"<span style='color:{C_PURPLE};font-weight:700;font-size:9px;'>"
                f"1 SOUL (CONTAINED)</span></span>"
            )
        else:
            self._refresh_count()

    def _refresh_count(self, count_color: str = C_ORANGE) -> None:
        if getattr(self, "_is_contained", False):
            return
        self._count_label.setText(
            f"<span style='color:{C_DIM};font-size:8px;font-family:monospace;'>"
            f"TREATS COLLECTED: "
            f"<span style='color:{count_color};font-weight:700;font-size:9px;'>"
            f"{self._count}</span> SOULS</span>"
        )

    def shake(self) -> None:
        start = self._pumpkin.pos()
        if self._shake_animation is not None:
            self._shake_animation.stop()
        animation = QPropertyAnimation(self._pumpkin, b"pos", self)
        animation.setDuration(320)
        animation.setLoopCount(1)
        animation.setKeyValueAt(0.0, start)
        animation.setKeyValueAt(0.15, start + QPoint(-3, 0))
        animation.setKeyValueAt(0.30, start + QPoint(3, 0))
        animation.setKeyValueAt(0.45, start + QPoint(-2, 0))
        animation.setKeyValueAt(0.60, start + QPoint(2, 0))
        animation.setKeyValueAt(1.0, start)
        self._shake_animation = animation
        animation.start()

    def add_treats(self, amount: int = 1) -> None:
        self._count += amount
        if not getattr(self, "_is_contained", False):
            self._refresh_count(C_GREEN)
            QTimer.singleShot(420, self._refresh_count)


class SpeechBubble(QFrame):
    poke_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(C_GREEN)
        self.setMinimumHeight(104)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 12, 8)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self._tag = _label("● RAM GLUTTON DETECTED", C_GREEN, 9, bold=True)
        self._tag.setStyleSheet(
            f"color: {C_GREEN}; font-size: 9px; font-weight: 700; letter-spacing: 1px; background: transparent;"
        )
        self._hour = _label("WITCHING HOUR", C_DIM, 8)
        top.addWidget(self._tag)
        top.addStretch(1)
        top.addWidget(self._hour)

        self._text = _label(
            '"Trick or Treat! Chrome is devouring 5GB of candy souls."',
            C_TEXT,
            11,
            italic=True,
        )
        self._text.setWordWrap(True)
        self._text.setMinimumHeight(34)
        self._text.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 3, 0, 0)
        footer.setSpacing(4)
        self._threat = QLabel()
        self._threat.setTextFormat(Qt.TextFormat.RichText)
        self._threat.setStyleSheet(
            f"color: {C_DIM}; font-size: 9px; background: transparent;"
        )
        self._poke = QPushButton("poke kiro 🍬")
        self._poke.setFlat(True)
        self._poke.setCursor(Qt.CursorShape.PointingHandCursor)
        self._poke.setStyleSheet(
            _style(
                "QPushButton {"
                " color: @DIM@;"
                " background: transparent;"
                " border: none;"
                " font-size: 9px;"
                " padding: 0;"
                "}"
                "QPushButton:hover { color: @PURPLE@; }"
            )
        )
        self._poke.clicked.connect(self.poke_requested.emit)
        footer.addWidget(self._threat)
        footer.addStretch(1)
        footer.addWidget(self._poke)

        layout.addLayout(top)
        layout.addWidget(self._text, 1)
        layout.addLayout(footer)
        self.set_taunt(
            "RAM GLUTTON DETECTED",
            '"Trick or Treat! Chrome is devouring 5GB of candy souls."',
            "FEASTING",
            C_GREEN,
        )

    def set_taunt(
        self,
        tag: str,
        text: str,
        threat: str,
        accent: str,
        hour: str = "WITCHING HOUR",
    ) -> None:
        self._accent = QColor(accent)
        self._tag.setText(f"● {tag}")
        self._tag.setStyleSheet(
            f"color: {accent}; font-size: 9px; font-weight: 700; letter-spacing: 1px; background: transparent;"
        )
        self._hour.setText(hour)
        self._text.setText(text)
        self._threat.setText(
            f"Threat: <span style='color:{accent};font-weight:700;'>{threat}</span>"
        )
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = QPainterPath()
        path.addRoundedRect(rect, 8.0, 8.0)

        painter.setPen(QPen(self._accent, 1.1))
        painter.setBrush(QColor(11, 8, 19, 242))
        painter.drawPath(path)


class MascotPanel(QFrame):
    poke_requested = pyqtSignal()
    mascot_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            _style(
                "MascotPanel {"
                " background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                " stop:0 rgba(18, 11, 29, 170),"
                " stop:0.5 rgba(27, 17, 43, 190),"
                " stop:1 rgba(18, 11, 29, 170));"
                " border-bottom: 1px solid @BORDER@;"
                "}"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)

        self.bubble = SpeechBubble()
        self.bubble.poke_requested.connect(self.poke_requested.emit)

        layout.addWidget(self.bubble, 1)

    def set_taunt(
        self,
        tag: str,
        text: str,
        threat: str,
        accent: str,
        hour: str = "WITCHING HOUR",
    ) -> None:
        self.bubble.set_taunt(tag, text, threat, accent, hour)


class ProcessRowWidget(QFrame):
    kill_requested = pyqtSignal(int)
    selected = pyqtSignal(int)

    def __init__(
        self,
        row: ProcessRow,
        stripe: bool = False,
        depth: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._row = row
        self._stripe = stripe
        self._depth = depth
        self._selected = False
        self._cursed = False
        self._branch = False
        self._accent = C_DIM
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{row.name} (PID {row.pid})")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(0)

        self._pid = _label(str(row.pid), C_DIM, 10)
        self._pid.setFixedWidth(55)
        layout.addWidget(self._pid)

        name_box = QWidget()
        name_box.setStyleSheet("background: transparent;")
        name_layout = QHBoxLayout(name_box)
        name_layout.setContentsMargins(depth * 11, 0, 0, 0)
        name_layout.setSpacing(6)
        self._dot = QLabel()
        self._dot.setFixedSize(6, 6)
        self._name = _label(row.name, C_TEXT, 10, bold=True)
        self._tag = _label("", C_DIM, 9)
        self._port = _label("", C_ORANGE, 8, bold=True)
        self._port.setStyleSheet(
            f"color: {C_ORANGE};"
            f" border: 1px solid {C_ORANGE};"
            " border-radius: 3px;"
            " padding: 0 3px;"
            " font-size: 8px;"
            " font-weight: 700;"
        )
        self._port.hide()
        name_layout.addWidget(self._dot)
        name_layout.addWidget(self._name)
        name_layout.addWidget(self._tag)
        name_layout.addWidget(self._port)
        name_layout.addStretch(1)
        layout.addWidget(name_box, 1)

        self._cpu = _label("", C_DIM, 10)
        self._cpu.setFixedWidth(58)
        self._cpu.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._cpu)

        self._mem = _label("", C_DIM, 10)
        self._mem.setFixedWidth(58)
        self._mem.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._mem)

        action_box = QWidget()
        action_box.setStyleSheet("background: transparent;")
        action_layout = QHBoxLayout(action_box)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(0)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kill = QPushButton("☠")
        self._kill.setFixedSize(22, 20)
        self._kill.setCursor(Qt.CursorShape.PointingHandCursor)
        self._kill.setToolTip("Exorcise process")
        self._kill.clicked.connect(
            lambda: self.kill_requested.emit(self._row.pid)
        )
        self._kill_effect = QGraphicsOpacityEffect(self._kill)
        self._kill_effect.setOpacity(0.0)
        self._kill.setGraphicsEffect(self._kill_effect)
        action_layout.addWidget(self._kill)
        action_box.setFixedWidth(38)
        layout.addWidget(action_box)

        self.set_data(row)
        self._apply_style()

    def set_data(
        self,
        row: ProcessRow,
        cursed: bool = False,
        branch: bool = False,
    ) -> None:
        self._row = row
        self._cursed = cursed
        self._branch = branch
        self._pid.setText(str(row.pid))
        display_name = row.name if len(row.name) <= 22 else f"{row.name[:21]}…"
        self._name.setText(display_name)
        self._name.setToolTip(row.name)

        details = [f"{row.name} (PID {row.pid})", f"ppid {row.ppid}"]
        if row.rss_mb:
            details.append(f"{row.rss_mb:.0f} MB RSS")
        details.append(f"{row.num_threads} threads")
        if row.ports:
            details.append("ports " + ", ".join(str(port) for port in row.ports))
        self.setToolTip(" · ".join(details))

        if cursed:
            accent = C_ICY
            tag = "(cursed)"
        elif row.status == psutil.STATUS_ZOMBIE:
            accent = C_PURPLE
            tag = "(zombie)"
        elif row.leak:
            accent = C_PURPLE
            tag = "LEAK"
        elif row.cpu >= CPU_SPIKE:
            accent = C_ORANGE
            tag = "(curse)"
        elif row.mem >= MEM_SPIKE:
            accent = C_GREEN
            tag = "(glutton)"
        else:
            accent = C_DIM
            tag = ""

        self._accent = accent
        self._dot.setStyleSheet(
            f"background: {accent}; border-radius: 3px;"
        )
        self._tag.setText(tag)
        self._tag.setStyleSheet(
            f"color: {accent}; font-size: 9px; background: transparent;"
        )

        haunted = row.haunted_ports
        if haunted:
            self._port.setText(":" + "/".join(str(port) for port in haunted[:2]))
            self._port.setToolTip(
                ", ".join(f"{port}:{HAUNTED_PORTS[port]}" for port in haunted)
            )
            self._port.show()
        else:
            self._port.hide()

        self._cpu.setText(f"{row.cpu:.1f}%")
        self._cpu.setStyleSheet(
            f"color: {accent if row.cpu >= CPU_SPIKE else C_DIM};"
            f" font-size: 10px;"
            f" font-weight: {'700' if row.cpu >= CPU_SPIKE else '400'};"
            " background: transparent;"
        )
        self._mem.setText(f"{row.mem:.1f}%")
        self._mem.setStyleSheet(
            f"color: {accent if row.mem >= MEM_SPIKE else C_DIM};"
            f" font-size: 10px;"
            f" font-weight: {'700' if row.mem >= MEM_SPIKE else '400'};"
            " background: transparent;"
        )
        self._kill.setStyleSheet(
            f"QPushButton {{"
            f" color: {accent};"
            f" background: rgba(189, 0, 255, 28);"
            f" border: 1px solid {accent};"
            f" border-radius: 4px;"
            f" font-size: 10px;"
            f"}}"
            f"QPushButton:hover {{"
            f" color: {C_VOID};"
            f" background: {accent};"
            f"}}"
        )
        self._sync_kill_visibility()
        self._apply_style()

    def _sync_kill_visibility(self) -> None:
        always = self._selected or self._row.squatter
        self._kill_effect.setOpacity(1.0 if always else 0.0)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._sync_kill_visibility()
        self._apply_style()

    def _apply_style(self) -> None:
        if self._cursed:
            background = "rgba(125, 233, 255, 32)"
            border = C_ICY
            pid_color = C_ICY
            name_color = C_ICY
        elif self._selected:
            background = "rgba(189, 0, 255, 34)"
            border = C_PURPLE
            pid_color = C_TEXT
            name_color = C_TEXT
        else:
            background = "rgba(18, 11, 29, 95)" if self._stripe else "transparent"
            border = C_ICY if self._branch else "transparent"
            pid_color = C_DIM
            name_color = C_TEXT

        self.setStyleSheet(
            f"ProcessRowWidget {{"
            f" background: {background};"
            f" border-left: 2px solid {border};"
            f" border-bottom: 1px solid rgba(56, 37, 74, 110);"
            f"}}"
            f"ProcessRowWidget:hover {{"
            f" background: rgba(56, 37, 74, 110);"
            f"}}"
        )
        self._pid.setStyleSheet(
            f"color: {pid_color}; font-size: 10px; background: transparent;"
        )
        self._name.setStyleSheet(
            f"color: {name_color}; font-size: 10px; font-weight: 600; background: transparent;"
        )

    def enterEvent(self, event) -> None:
        self._kill_effect.setOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        cursor_inside = self.rect().contains(
            self.mapFromGlobal(QCursor.pos())
        )
        if not self._selected and not self._row.squatter and not cursor_inside:
            self._kill_effect.setOpacity(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._row.pid)
        super().mousePressEvent(event)


class ProcessTable(QFrame):
    kill_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[ProcessRowWidget] = []
        self._pids: list[int] = []
        self._depths: dict[int, int] = {}
        self._cursed_pids: set[int] = set()
        self._branch_pids: set[int] = set()
        self._selected_pid: int | None = None
        self.setMinimumHeight(220)
        self.setStyleSheet("background: rgba(11, 8, 19, 155); border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(27)
        header.setStyleSheet(
            _style(
                "background: rgba(18, 11, 29, 235);"
                " border-bottom: 1px solid @BORDER@;"
            )
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 10, 0)
        header_layout.setSpacing(0)
        pid = _label("PID", C_DIM, 9, bold=True)
        pid.setFixedWidth(55)
        header_layout.addWidget(pid)
        process = _label("HAUNTED PROCESS", C_DIM, 9, bold=True)
        header_layout.addWidget(process, 1)
        cpu = _label("CPU%", C_ORANGE, 9, bold=True)
        cpu.setFixedWidth(58)
        cpu.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header_layout.addWidget(cpu)
        mem = _label("MEM%", C_GREEN, 9, bold=True)
        mem.setFixedWidth(58)
        mem.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header_layout.addWidget(mem)
        act = _label("ACT", C_DIM, 9, bold=True)
        act.setFixedWidth(38)
        act.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(act)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._scroll.viewport().setAutoFillBackground(False)

        self._body = QWidget()
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addStretch(1)
        self._scroll.setWidget(self._body)

        layout.addWidget(header)
        layout.addWidget(self._scroll, 1)

    def update_rows(
        self,
        processes: list[ProcessRow],
        cursed_pids: set[int] | None = None,
        depths: dict[int, int] | None = None,
        branch_pids: set[int] | None = None,
    ) -> None:
        if cursed_pids is not None:
            self._cursed_pids = set(cursed_pids)
        depths = depths or {}
        if branch_pids is not None:
            self._branch_pids = set(branch_pids)

        pids = [row.pid for row in processes]
        if pids != self._pids or depths != self._depths:
            self._depths = dict(depths)
            self._rebuild(processes)
            return

        for widget, row in zip(self._rows, processes):
            widget.set_data(
                row,
                cursed=row.pid in self._cursed_pids,
                branch=row.pid in self._branch_pids,
            )

    def set_cursed_pids(self, pids: set[int]) -> None:
        self._cursed_pids = set(pids)
        for widget in self._rows:
            widget.set_data(
                widget._row,
                cursed=widget._row.pid in self._cursed_pids,
                branch=widget._row.pid in self._branch_pids,
            )

    def set_branch_pids(self, pids: set[int]) -> None:
        self._branch_pids = set(pids)
        for widget in self._rows:
            widget.set_data(
                widget._row,
                cursed=widget._row.pid in self._cursed_pids,
                branch=widget._row.pid in self._branch_pids,
            )

    def _rebuild(self, processes: list[ProcessRow]) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._rows = []
        self._pids = [row.pid for row in processes]

        if not processes:
            empty = _label("The process table is empty… for now.", C_DIM, 10, italic=True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setFixedHeight(80)
            self._body_layout.addWidget(empty)
            self._body_layout.addStretch(1)
            self._selected_pid = None
            return

        for index, row in enumerate(processes):
            widget = ProcessRowWidget(
                row,
                stripe=index % 2 == 1,
                depth=self._depths.get(row.pid, 0),
            )
            widget.set_data(
                row,
                cursed=row.pid in self._cursed_pids,
                branch=row.pid in self._branch_pids,
            )
            widget.kill_requested.connect(self.kill_requested.emit)
            widget.selected.connect(self.select_pid)
            self._body_layout.addWidget(widget)
            self._rows.append(widget)
        self._body_layout.addStretch(1)

        if self._selected_pid not in self._pids:
            self._selected_pid = self._pids[0]
        self._sync_selection()

    def _sync_selection(self) -> None:
        for widget in self._rows:
            widget.set_selected(widget._row.pid == self._selected_pid)

    def select_pid(self, pid: int) -> None:
        if pid == self._selected_pid:
            return
        self._selected_pid = pid
        self._sync_selection()

    def selected_pid(self) -> int | None:
        return self._selected_pid

    def move_selection(self, delta: int) -> None:
        if not self._pids:
            return
        try:
            index = self._pids.index(self._selected_pid)
        except ValueError:
            index = 0
        index = max(0, min(len(self._pids) - 1, index + delta))
        self.select_pid(self._pids[index])
        widget = self._rows[index]
        self._scroll.ensureWidgetVisible(widget, 0, 30)


class CryptRow(QFrame):
    resurrect_requested = pyqtSignal(object)

    def __init__(self, entry: CryptEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setFixedHeight(32)
        self.setStyleSheet(
            _style(
                "CryptRow {"
                " background: rgba(18, 11, 29, 105);"
                " border-bottom: 1px solid rgba(56, 37, 74, 100);"
                "}"
                "CryptRow:hover { background: rgba(56, 37, 74, 90); }"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(0)

        pid = QLabel(f"<s>{entry.pid}</s>")
        pid.setTextFormat(Qt.TextFormat.RichText)
        pid.setFixedWidth(55)
        pid.setStyleSheet("color: rgba(168, 156, 185, 130); font-size: 10px; background: transparent;")
        layout.addWidget(pid)

        name = QLabel(f"🪦 <s>{_escape(entry.name)}</s>")
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setStyleSheet(f"color: {C_DIM}; font-size: 10px; background: transparent;")
        layout.addWidget(name, 1)

        signal_label = _label(entry.signal, C_DIM, 9)
        signal_label.setFixedWidth(58)
        signal_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(signal_label)

        button = QPushButton("⚡ Resurrect")
        button.setFixedSize(92, 22)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            _style(
                "QPushButton {"
                " color: @PURPLE@;"
                " background: rgba(189, 0, 255, 34);"
                " border: 1px solid rgba(189, 0, 255, 120);"
                " border-radius: 4px;"
                " font-size: 9px;"
                " font-weight: 600;"
                "}"
                "QPushButton:hover {"
                " color: @VOID@;"
                " background: @PURPLE@;"
                "}"
            )
        )
        button.clicked.connect(
            lambda: self.resurrect_requested.emit(self.entry)
        )
        layout.addSpacing(6)
        layout.addWidget(button)


class CryptPanel(QFrame):
    resurrect_requested = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[CryptRow] = []
        self.setMinimumHeight(145)
        self.setStyleSheet(
            _style(
                "CryptPanel {"
                " background: rgba(10, 7, 18, 240);"
                " border-top: 2px solid @BORDER@;"
                "}"
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(30)
        header.setStyleSheet(
            _style(
                "background: rgba(18, 11, 29, 235);"
                " border-bottom: 1px solid rgba(56, 37, 74, 180);"
            )
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 0, 12, 0)
        header_layout.setSpacing(6)

        title = QLabel("🪦 THE CRYPT &amp; CEMETERY")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet(
            f"color: {C_TEXT}; font-size: 9px; font-weight: 800; letter-spacing: 1px; background: transparent;"
        )
        self._count = _label("(0 slain)", C_DIM, 9)
        header_layout.addWidget(title)
        header_layout.addWidget(self._count)
        header_layout.addStretch(1)
        souls = QLabel("⚰️ SOULS IN PURGATORY")
        souls.setTextFormat(Qt.TextFormat.RichText)
        souls.setStyleSheet(
            f"color: {C_PURPLE}; font-size: 8px; font-weight: 700; letter-spacing: 1px; background: transparent;"
        )
        header_layout.addWidget(souls)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self._scroll.viewport().setAutoFillBackground(False)

        self._body = QWidget()
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addStretch(1)
        self._scroll.setWidget(self._body)

        layout.addWidget(header)
        layout.addWidget(self._scroll, 1)

    def add_entry(self, pid: int, name: str, signal_name: str) -> None:
        entry = CryptEntry(pid=pid, name=name, signal=signal_name)
        row = CryptRow(entry)
        row.resurrect_requested.connect(self._on_resurrect)
        self._body_layout.insertWidget(0, row)
        self._rows.insert(0, row)
        while len(self._rows) > 18:
            old = self._rows.pop()
            self._body_layout.removeWidget(old)
            old.deleteLater()
        self._update_count()

    def _on_resurrect(self, entry: CryptEntry) -> None:
        self._remove_entry(entry)
        self.resurrect_requested.emit(entry)

    def _remove_entry(self, entry: CryptEntry) -> None:
        for row in list(self._rows):
            if row.entry is entry:
                self._rows.remove(row)
                self._body_layout.removeWidget(row)
                row.deleteLater()
                break
        self._update_count()

    def resurrect_latest(self) -> None:
        if self._rows:
            self._on_resurrect(self._rows[0].entry)

    def _update_count(self) -> None:
        self._count.setText(f"({len(self._rows)} slain)")


class FooterBar(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            _style(
                "FooterBar {"
                " background: rgba(11, 8, 19, 240);"
                " border-top: 1px solid @BORDER@;"
                " border-bottom-left-radius: 14px;"
                " border-bottom-right-radius: 14px;"
                "}"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        for key, action in (
            ("k", "Exorcise"),
            ("c", "Curse"),
            ("T", "Trace"),
            ("r", "Resurrect"),
            ("s", "Spook"),
            ("m", "Mute"),
        ):
            layout.addWidget(self._hint(key, action))

        layout.addStretch(1)

        self._dot = QLabel()
        self._dot.setFixedSize(6, 6)
        self._dot.setStyleSheet(
            f"background: {C_GREEN}; border-radius: 3px;"
        )
        self._audio = _label("AUDIO: PROBING", C_DIM, 8, bold=True)
        layout.addWidget(self._dot)
        layout.addWidget(self._audio)

    def _hint(self, key: str, action: str) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        kbd = QLabel(key)
        kbd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        kbd.setFixedSize(14, 14)
        kbd.setStyleSheet(
            _style(
                "color: @TEXT@;"
                " background: rgba(56, 37, 74, 220);"
                " border-radius: 3px;"
                " font-size: 9px;"
                " font-weight: 700;"
            )
        )
        row.addWidget(kbd)
        row.addWidget(_label(action, C_DIM, 8))
        return widget

    def set_audio_status(self, text: str, color: str = C_GREEN) -> None:
        self._audio.setText(text)
        self._audio.setStyleSheet(
            f"color: {color}; font-size: 8px; font-weight: 700; background: transparent;"
        )
        self._dot.setStyleSheet(f"background: {color}; border-radius: 3px;")


class GhostSwarm(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def burst(self, count: int = 7) -> None:
        if self.parentWidget() is None:
            return
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        glyphs = ["👻", "🎃", "💀", "🕸️", "🦇"]
        for _ in range(count):
            label = QLabel(random.choice(glyphs), self)
            size = random.randint(17, 30)
            label.setStyleSheet(
                f"font-size: {size}px; background: transparent; border: none;"
            )
            label.adjustSize()
            x = random.randint(8, max(9, self.width() - label.width() - 8))
            y = self.height() - random.randint(20, 90)
            label.move(x, y)
            label.show()

            effect = QGraphicsOpacityEffect(label)
            effect.setOpacity(1.0)
            label.setGraphicsEffect(effect)

            group = QParallelAnimationGroup(self)
            movement = QPropertyAnimation(label, b"pos", group)
            movement.setDuration(random.randint(1400, 2400))
            movement.setStartValue(QPoint(x, y))
            movement.setEndValue(
                QPoint(
                    x + random.randint(-45, 45),
                    y - random.randint(230, 430),
                )
            )
            movement.setEasingCurve(QEasingCurve.Type.OutCubic)

            fade = QPropertyAnimation(effect, b"opacity", group)
            fade.setDuration(movement.duration())
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)

            group.addAnimation(movement)
            group.addAnimation(fade)
            group.finished.connect(
                lambda lbl=label, grp=group: self._cleanup(lbl, grp)
            )
            group.start()

    def _cleanup(self, label: QLabel, group: QParallelAnimationGroup) -> None:
        label.deleteLater()
        group.deleteLater()


class DraggableGhost(QLabel):
    clicked = pyqtSignal()
    captured = pyqtSignal()
    escaped = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, bucket: CandyBanner | None = None) -> None:
        super().__init__(parent)
        self._bucket = bucket
        self.setFixedSize(78, 78)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Drag Kiro into the Soul Candy Bucket to capture it!")

        self._drag_start_pos: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._is_dragging: bool = False
        self._is_captured: bool = False
        self._group: QParallelAnimationGroup | None = None

        self._movie = _load_ghost_movie(QSize(78, 78))
        if self._movie is not None:
            self.setMovie(self._movie)
            self._movie.start()
        else:
            self.setText("👻")
            self.setStyleSheet("font-size: 48px; background: transparent;")

    def set_bucket(self, bucket: CandyBanner) -> None:
        self._bucket = bucket

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        aura = QRadialGradient(center, self.width() / 2.0)
        aura.setColorAt(0.0, QColor(57, 255, 20, 80))
        aura.setColorAt(0.45, QColor(189, 0, 255, 70))
        aura.setColorAt(1.0, QColor(255, 122, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(aura)
        painter.drawEllipse(center, self.width() / 2.0, self.height() / 2.0)
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_offset = event.position().toPoint()
            self._is_dragging = False
            self.stop_patrol()
            self.raise_()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            if not self._is_dragging and getattr(self, "_drag_start_global", None) is not None:
                if (event.globalPosition().toPoint() - self._drag_start_global).manhattanLength() > 3:
                    self._is_dragging = True

            if self._is_dragging:
                parent = self.parentWidget()
                if parent is not None:
                    parent_pt = parent.mapFromGlobal(event.globalPosition().toPoint())
                    new_x = parent_pt.x() - self._drag_offset.x()
                    new_y = parent_pt.y() - self._drag_offset.y()
                    max_x = max(0, parent.width() - self.width())
                    max_y = max(0, parent.height() - self.height())
                    self.move(max(0, min(new_x, max_x)), max(0, min(new_y, max_y)))
                else:
                    self.move(self.pos() + event.position().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        was_dragging = self._is_dragging
        self._drag_offset = None
        self._drag_start_global = None
        self._is_dragging = False

        if event.button() == Qt.MouseButton.LeftButton:
            if self._check_collision():
                self.capture()
                return
            elif was_dragging:
                self.start_patrol()
            else:
                self.clicked.emit()
                self.start_patrol()

        super().mouseReleaseEvent(event)

    def _check_collision(self) -> bool:
        if self._bucket is None:
            return False
        pumpkin = getattr(self._bucket, "pumpkin_label", None) or getattr(self._bucket, "_pumpkin", None)
        if pumpkin is None or not pumpkin.isVisible():
            return False

        ghost_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
        pumpkin_rect = QRect(pumpkin.mapToGlobal(QPoint(0, 0)), pumpkin.size())
        return ghost_rect.intersects(pumpkin_rect.adjusted(-12, -12, 12, 12))

    def capture(self) -> None:
        self._is_captured = True
        self.stop_patrol()
        self.hide()
        if self._bucket is not None:
            self._bucket.set_contained(True)
            self._bucket.shake()
        self.captured.emit()
        QTimer.singleShot(random.randint(1000, 20000), self.escape)

    def escape(self) -> None:
        if not self._is_captured:
            return
        self._is_captured = False

        parent = self.parentWidget()
        if parent is not None:
            max_x = max(0, parent.width() - self.width())
            max_y = max(0, parent.height() - self.height())
            rand_x = random.randint(0, max_x)
            rand_y = random.randint(0, max_y)
            self.move(rand_x, rand_y)

        self.show()
        self.raise_()

        if self._bucket is not None:
            self._bucket.set_contained(False)

        self.escaped.emit()
        self.start_patrol()

    def start_patrol(self) -> None:
        if self._is_captured:
            return
        parent = self.parentWidget()
        if parent is None or parent.width() < 220 or parent.height() < 220:
            return
        width = parent.width()
        height = parent.height()

        def point(fx: float, fy: float) -> QPoint:
            x = int((width - self.width()) * fx)
            y = int((height - self.height()) * fy)
            return QPoint(
                max(0, min(x, width - self.width())),
                max(0, min(y, height - self.height())),
            )

        start_pt = self.pos()
        if start_pt == QPoint(0, 0):
            start_pt = point(0.10, 0.10)

        path = [
            start_pt,
            point(0.58, 0.14),
            point(0.85, 0.38),
            point(0.62, 0.60),
            point(0.18, 0.78),
            point(0.06, 0.40),
            point(0.10, 0.10),
            start_pt,
        ]

        if self._group is not None:
            self._group.stop()
            self._group.deleteLater()

        group = QParallelAnimationGroup(self)
        group.setLoopCount(-1)

        movement = QPropertyAnimation(self, b"pos", group)
        movement.setDuration(18000)
        movement.setEasingCurve(QEasingCurve.Type.InOutSine)
        for index, position in enumerate(path):
            movement.setKeyValueAt(index / (len(path) - 1), position)
        group.addAnimation(movement)

        self._group = group
        self.show()
        self.raise_()
        group.start()

    def stop_patrol(self) -> None:
        if self._group is not None:
            self._group.stop()
            self._group.deleteLater()
            self._group = None


FlyingKiro = DraggableGhost


class TraceBanner(QFrame):
    cleared = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setVisible(False)
        self.setStyleSheet(
            _style(
                "TraceBanner {"
                " background: rgba(125, 233, 255, 24);"
                " border-bottom: 1px solid @ICY@;"
                "}"
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        self._label = _label("", C_ICY, 9, bold=True)
        layout.addWidget(self._label, 1)

        close = QPushButton("✕")
        close.setFixedSize(18, 18)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("End bloodline trace")
        close.setStyleSheet(
            f"QPushButton {{ color: {C_ICY}; background: transparent;"
            f" border: none; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {C_VOID}; background: {C_ICY};"
            " border-radius: 3px; }"
        )
        close.clicked.connect(self.cleared.emit)
        layout.addWidget(close)

    def show_trace(
        self, root: ProcessRow, count: int, leaking: bool
    ) -> None:
        suffix = " · LEAK IN LINEAGE" if leaking else ""
        self._label.setText(
            f"BLOODLINE: {root.name} (PID {root.pid}) · {count} kin{suffix}"
        )
        self.setVisible(True)

    def clear_trace(self) -> None:
        self.setVisible(False)


class GtopWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gtop — Haunted Process Monitor")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(480, 820)

        self._audio = AudioEngine()
        self._snapshot = SystemSnapshot()
        self._taunt_hold_until = 0.0
        self._last_whisper = ""
        self._get_whispers = None
        self._ambient_whisper = ""
        self._shake_animation: QPropertyAnimation | None = None
        self._shortcuts: list[QShortcut] = []
        self._cursed_pids: set[int] = set()
        self._trace_root: int | None = None

        root = QWidget(self)
        root.setObjectName("gtopRoot")
        root.setStyleSheet("background: transparent;")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("windowFrame")
        self._frame.setStyleSheet(
            _style(
                "QFrame#windowFrame {"
                " background-color: rgba(15, 20, 28, 180);"
                " border: 1px solid @BORDER@;"
                " border-radius: 14px;"
                "}"
            )
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 190))
        self._frame.setGraphicsEffect(shadow)
        root_layout.addWidget(self._frame)

        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self.header = HeaderBar()
        self.banner = CandyBanner()
        self.mascot_panel = MascotPanel()

        gauges = QWidget()
        gauges.setFixedHeight(84)
        gauges.setStyleSheet(
            _style(
                "background: rgba(11, 8, 19, 120);"
                " border-bottom: 1px solid @BORDER@;"
            )
        )
        gauges_layout = QHBoxLayout(gauges)
        gauges_layout.setContentsMargins(10, 9, 10, 9)
        gauges_layout.setSpacing(8)
        self.cpu_card = GaugeCard(
            "🔥",
            "CORE HEAT (CPU)",
            C_ORANGE,
            ("#FF7A00", "#FF9E00", "#FF5E00"),
        )
        self.ram_card = GaugeCard(
            "🧪",
            "SOUL POOL (RAM)",
            C_GREEN,
            ("#39FF14", "#70FF47", "#39FF14"),
        )
        gauges_layout.addWidget(self.cpu_card, 1)
        gauges_layout.addWidget(self.ram_card, 1)

        self.trace = TraceBanner()
        self.table = ProcessTable()
        self.crypt = CryptPanel()
        self.footer = FooterBar()

        frame_layout.addWidget(self.header)
        frame_layout.addWidget(self.banner)
        frame_layout.addWidget(self.mascot_panel)
        frame_layout.addWidget(gauges)
        frame_layout.addWidget(self.trace)
        frame_layout.addWidget(self.table, 1)
        frame_layout.addWidget(self.crypt)
        frame_layout.addWidget(self.footer)

        self._decor = DecorOverlay(self._frame)
        self._swarm = GhostSwarm(self._frame)
        self._flyer = DraggableGhost(self._frame, bucket=self.banner)
        self._decor.setGeometry(self._frame.rect())
        self._swarm.setGeometry(self._frame.rect())
        self._decor.raise_()
        self._flyer.raise_()

        self._wire_events()
        self._install_shortcuts()

        self.crypt.add_entry(5523, "slack-renderer", "SIGTERM")
        self.crypt.add_entry(821, "docker-daemon", "SIGKILL")

        try:
            self._apply_snapshot(_collect_snapshot())
        except Exception:
            pass

        try:
            from spookcli.whispers import (
                _AMBIENT_WHISPER,
                get_current_whispers,
                start_whispers,
            )

            self._get_whispers = get_current_whispers
            self._ambient_whisper = _AMBIENT_WHISPER
            start_whispers()
        except Exception:
            self._get_whispers = None
            self._ambient_whisper = ""

        self._whisper_timer = QTimer(self)
        self._whisper_timer.setInterval(int(WHISPER_SECS * 1000))
        self._whisper_timer.timeout.connect(self._poll_whisper)
        self._whisper_timer.start()

        self._worker = SnapshotWorker(self)
        self._worker.snapshot_ready.connect(self._apply_snapshot)
        self._worker.start()
        self._audio.play_loop("Possessed_High_Score.mp3", 0.25)


        QTimer.singleShot(250, self._refresh_audio_status)

    def _wire_events(self) -> None:
        self.header.minimize_requested.connect(self.showMinimized)
        self.header.close_requested.connect(self.close)
        self.header.spook_requested.connect(self.spook)
        self.header.audio_muted.connect(self._on_audio_muted)
        self.banner.spook_requested.connect(self.spook)
        self.banner.bucket_clicked.connect(self._on_bucket)
        self._flyer.clicked.connect(self._on_flying_kiro)
        self._flyer.captured.connect(self._on_ghost_captured)
        self._flyer.escaped.connect(self._on_ghost_escaped)
        self.mascot_panel.mascot_clicked.connect(self.cycle_taunt)
        self.mascot_panel.poke_requested.connect(self.cycle_taunt)
        self.table.kill_requested.connect(self._exorcise)
        self.crypt.resurrect_requested.connect(self._on_resurrect)
        self.trace.cleared.connect(self._clear_trace)

    def _install_shortcuts(self) -> None:
        bindings = (
            ("k", self._exorcise_selected),
            ("c", self._toggle_curse),
            ("r", self._resurrect_selected),
            ("s", self.spook),
            ("m", self._toggle_mute),
            ("Shift+T", self._toggle_trace),
            ("q", self.close),
            ("Escape", self.close),
            ("Up", lambda: self.table.move_selection(-1)),
            ("Down", lambda: self.table.move_selection(1)),
        )
        for sequence, handler in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _apply_snapshot(self, snapshot: object) -> None:
        if not isinstance(snapshot, SystemSnapshot):
            return
        self._snapshot = snapshot

        self.header.set_metrics(snapshot.cpu_total, snapshot.mem_percent)
        self._refresh_table()

        cores = snapshot.core_count or (psutil.cpu_count(logical=True) or 0)
        cpu_status = (
            "CRITICAL"
            if snapshot.cpu_total >= 80
            else "ELEVATED"
            if snapshot.cpu_total >= 50
            else "STABLE"
        )
        self.cpu_card.set_metrics(
            snapshot.cpu_total,
            f"{snapshot.cpu_total:.1f}%",
            f"{cores} CORES CURSED",
            cpu_status,
        )
        self.ram_card.set_metrics(
            snapshot.mem_percent,
            f"{snapshot.mem_used_gb:.1f} / {snapshot.mem_total_gb:.0f}GB",
            "ECTOPLASM OVERFLOW"
            if snapshot.mem_percent >= 80
            else "SOUL POOL STABLE",
            f"{snapshot.mem_percent:.0f}%",
        )

        if time.monotonic() >= self._taunt_hold_until:
            self._update_snapshot_taunt(snapshot)

    def _refresh_table(self) -> None:
        traced = self._trace_rows()
        if traced is None:
            if self._trace_root is not None:
                self._trace_root = None
                self.trace.clear_trace()
            self.table.update_rows(
                self._snapshot.processes,
                cursed_pids=self._cursed_pids,
            )
            return

        processes = [row for row, _depth in traced]
        depths = {row.pid: depth for row, depth in traced}
        branch = self._leak_branch({row.pid for row in processes})
        self.table.update_rows(
            processes,
            cursed_pids=self._cursed_pids,
            depths=depths,
            branch_pids=branch,
        )
        leaking = self._snapshot.leak_pid in {row.pid for row in processes}
        self.trace.show_trace(traced[0][0], max(0, len(processes) - 1), leaking)

    def _trace_rows(self) -> list[tuple[ProcessRow, int]] | None:
        if self._trace_root is None:
            return None

        processes = self._snapshot.all_processes
        by_pid = {row.pid: row for row in processes}
        root = by_pid.get(self._trace_root)
        if root is None:
            return None

        children: dict[int, list[ProcessRow]] = {}
        for row in processes:
            children.setdefault(row.ppid, []).append(row)

        ordered: list[tuple[ProcessRow, int]] = []

        def walk(node: ProcessRow, depth: int) -> None:
            if len(ordered) >= TRACE_MAX_ROWS:
                return
            ordered.append((node, depth))
            for child in sorted(
                children.get(node.pid, []),
                key=lambda row: (-row.cpu, -row.mem),
            ):
                walk(child, depth + 1)

        walk(root, 0)
        return ordered

    def _leak_branch(self, visible_pids: set[int]) -> set[int]:
        leak_pid = self._snapshot.leak_pid
        if leak_pid is None or self._trace_root is None:
            return set()
        if leak_pid not in visible_pids:
            return set()

        by_pid = {row.pid: row for row in self._snapshot.all_processes}
        branch: set[int] = set()
        cursor: int | None = leak_pid
        while cursor is not None and cursor not in branch:
            branch.add(cursor)
            if cursor == self._trace_root:
                break
            node = by_pid.get(cursor)
            if node is None:
                break
            cursor = node.ppid
        return branch

    def _toggle_trace(self) -> None:
        pid = self.table.selected_pid()
        if pid is None:
            self._set_taunt(
                "NO BLOODLINE",
                '"Select a spirit before tracing its kin."',
                "PATIENT",
                C_DIM,
                3.0,
            )
            return

        if self._trace_root == pid:
            self._clear_trace()
            return

        by_pid = {row.pid: row for row in self._snapshot.all_processes}
        root = by_pid.get(pid)
        if root is None:
            self._set_taunt(
                "ALREADY GONE",
                f'"PID {pid} has no bloodline left to trace."',
                "VANISHED",
                C_DIM,
                3.0,
            )
            return

        self._trace_root = pid
        self._audio.play("collected.wav", 0.35)
        self._set_taunt(
            "BLOODLINE TRACED",
            f'"The kin of {root.name} reveal themselves. Follow the leaking branch."',
            "BOUND",
            C_ICY,
            5.0,
        )
        self._refresh_table()

    def _clear_trace(self) -> None:
        if self._trace_root is None and not self.trace.isVisible():
            return
        self._trace_root = None
        self.trace.clear_trace()
        self._refresh_table()
        self._set_taunt(
            "BLOODLINE SEVERED",
            '"The lineage fades back into the mist."',
            "RELEASED",
            C_DIM,
            3.0,
        )

    def _update_snapshot_taunt(self, snapshot: SystemSnapshot) -> None:
        if snapshot.zombie_pids:
            pid = snapshot.zombie_pids[0]
            text = random.choice(_TAUNTS["zombie"]).format(pid=pid)
            self._set_taunt("ZOMBIE DETECTED", text, "ROAMING", C_PURPLE, 5.0)
        elif (
            snapshot.leak_pid is not None
            and snapshot.leak_growth >= LEAK_GROWTH_MB
        ):
            leak = next(
                (
                    row
                    for row in snapshot.all_processes
                    if row.pid == snapshot.leak_pid
                ),
                None,
            )
            if leak is not None:
                self._set_taunt(
                    "BLOODLINE LEAK",
                    f'"PID {leak.pid} — {leak.name} is swelling with stolen souls'
                    f' (+{snapshot.leak_growth:.0f} MB, now {leak.rss_mb:.0f} MB)."',
                    "SWELLING",
                    C_PURPLE,
                    5.0,
                )
            else:
                self._set_taunt(
                    "IDLE",
                    random.choice(_TAUNTS["idle"]),
                    "WATCHFUL",
                    C_DIM,
                )
        elif snapshot.top_cpu is not None and snapshot.top_cpu.cpu >= CPU_SPIKE:
            proc = snapshot.top_cpu
            text = random.choice(_TAUNTS["cpu"]).format(
                name=proc.name, cpu=proc.cpu
            )
            self._set_taunt("CPU GLUTTON", text, "BURNING", C_ORANGE)
        elif snapshot.top_mem is not None and snapshot.top_mem.mem >= MEM_SPIKE:
            proc = snapshot.top_mem
            text = random.choice(_TAUNTS["ram"]).format(
                name=proc.name, mem=proc.mem
            )
            self._set_taunt("RAM GLUTTON DETECTED", text, "FEASTING", C_GREEN)
        elif snapshot.squatter_count:
            squatters = [row for row in snapshot.all_processes if row.squatter][:3]
            names = ", ".join(
                f"{row.name}:{row.haunted_ports[0]}" for row in squatters
            )
            self._set_taunt(
                "PORT HAUNTING",
                f'"Something is squatting on your ports: {names}."',
                "LISTENING",
                C_ORANGE,
                5.0,
            )
        else:
            self._set_taunt(
                "IDLE",
                random.choice(_TAUNTS["idle"]),
                "WATCHFUL",
                C_DIM,
            )

    def _poll_whisper(self) -> None:
        if self._get_whispers is None:
            return
        try:
            raw = self._get_whispers()
        except Exception:
            return
        if not raw or raw == self._ambient_whisper or raw == self._last_whisper:
            return
        if time.monotonic() < self._taunt_hold_until:
            return
        self._last_whisper = raw
        self._set_taunt(
            "OS ANOMALY",
            f'"{raw}"',
            "LINGERING",
            C_PURPLE,
            5.5,
        )

    def _set_taunt(
        self,
        tag: str,
        text: str,
        threat: str,
        accent: str,
        hold: float = 4.5,
    ) -> None:
        self.mascot_panel.set_taunt(tag, text, threat, accent)
        self._taunt_hold_until = time.monotonic() + hold

    def cycle_taunt(self) -> None:
        tag, text, threat, accent = random.choice(_POKE_QUOTES)
        self._set_taunt(tag, text, threat, accent, 6.0)
        self.banner.shake()
        self._audio.play("collected.wav", 0.25)

    def _on_bucket(self) -> None:
        self.banner.shake()
        self._audio.play("collected.wav", 0.4)
        if getattr(self.banner, "_is_contained", False):
            self._set_taunt(
                "SOUL CONTAINED",
                '"The bucket rattles violently! A captured soul is thrashing against the lid."',
                "THRASHING",
                C_PURPLE,
                4.0,
            )
        else:
            self.banner.add_treats(1)
            self._swarm.burst(3)
            self._set_taunt(
                "SOUL CANDY BUCKET",
                '"The bucket rattles. The souls are restless tonight."',
                "HUNGRY",
                C_ORANGE,
                4.0,
            )

    def _on_flying_kiro(self) -> None:
        self.banner.add_treats(3)
        self._audio.play("collected.wav", 0.45)
        self._swarm.burst(4)
        self._set_taunt(
            "TRICK OR TREAT",
            '"Kiro snatches a handful of soul candy and vanishes into the mist."',
            "GIGGLING",
            C_GREEN,
            4.0,
        )

    def _on_ghost_captured(self) -> None:
        self._audio.play("exorcism1.wav", 0.55)
        self.banner.shake()
        self._swarm.burst(6)
        self._set_taunt(
            "SOUL CONTAINED",
            '"You dragged the wandering ghost into the candy bucket! Contained... for now."',
            "CONTAINED",
            C_PURPLE,
            4.0,
        )

    def _on_ghost_escaped(self) -> None:
        self._audio.play("ghost_scream.wav", 0.55)
        self.banner.shake()
        self._swarm.burst(8)
        self._set_taunt(
            "GHOST ESCAPED",
            '"HEE HEE! The seal breaks! Kiro slips free back into the mist."',
            "FREE",
            C_GREEN,
            4.0,
        )

    def _toggle_curse(self) -> None:
        pid = self.table.selected_pid()
        if pid is None:
            self._set_taunt(
                "NO SPIRIT SELECTED",
                '"Choose a row to curse first, mortal."',
                "PATIENT",
                C_DIM,
                3.0,
            )
            return

        if pid in (0, 1, os.getpid()):
            self._set_taunt(
                "FORBIDDEN RITUAL",
                '"That soul is bound to the living world."',
                "SEALED",
                C_PURPLE,
                4.0,
            )
            return

        try:
            process = psutil.Process(pid)
            name = process.name() or f"pid-{pid}"
            if pid in self._cursed_pids:
                process.resume()
                self._cursed_pids.discard(pid)
                self._audio.play("collected.wav", 0.4)
                self._set_taunt(
                    "UNCURSED",
                    f'"PID {pid} — {name} lurches back into motion."',
                    "RELEASED",
                    C_GREEN,
                    4.0,
                )
            else:
                process.suspend()
                self._cursed_pids.add(pid)
                self._audio.play("exorcism2.wav", 0.4)
                self._set_taunt(
                    "CURSED",
                    f'"PID {pid} — {name} is frozen mid-scream."',
                    "BOUND",
                    C_ICY,
                    4.0,
                )
        except psutil.NoSuchProcess:
            self._cursed_pids.discard(pid)
            self._set_taunt(
                "ALREADY GONE",
                f'"PID {pid} was already a ghost."',
                "VANISHED",
                C_DIM,
                3.0,
            )
        except psutil.AccessDenied:
            self._set_taunt(
                "RESISTANCE",
                '"The spirit resists your icy grip."',
                "SHIELDED",
                C_PURPLE,
                4.0,
            )
        except Exception as exc:
            self._cursed_pids.discard(pid)
            self._set_taunt(
                "HEX FAILED",
                f'"The ritual fizzled: {type(exc).__name__}."',
                "UNSTABLE",
                C_DIM,
                4.0,
            )
        else:
            self.table.set_cursed_pids(self._cursed_pids)

    def _exorcise_selected(self) -> None:
        pid = self.table.selected_pid()
        if pid is None:
            self._set_taunt(
                "NO SPIRIT SELECTED",
                '"Choose a row first, mortal."',
                "PATIENT",
                C_DIM,
                3.0,
            )
            return
        self._exorcise(pid)

    def _exorcise(self, pid: int) -> None:
        if pid in (0, 1, os.getpid()):
            self._set_taunt(
                "FORBIDDEN RITUAL",
                '"That soul is bound to the living world."',
                "SEALED",
                C_PURPLE,
                4.0,
            )
            return

        try:
            process = psutil.Process(pid)
            name = process.name() or f"pid-{pid}"
            if pid in self._cursed_pids:
                with contextlib.suppress(Exception):
                    process.resume()
                self._cursed_pids.discard(pid)
                self.table.set_cursed_pids(self._cursed_pids)
            process.terminate()
            self.crypt.add_entry(pid, name, "SIGTERM")
            self.banner.add_treats(1)
            self._audio.play(
                random.choice(["exorcism1.wav", "exorcism2.wav"]), 0.6
            )
            self._set_taunt(
                "EXORCISED",
                f'"PID {pid} — {name} has been cast into the crypt."',
                "SLAIN",
                C_ORANGE,
                4.0,
            )
            self._swarm.burst(4)
        except psutil.NoSuchProcess:
            self._set_taunt(
                "ALREADY GONE",
                f'"PID {pid} was already a ghost."',
                "VANISHED",
                C_DIM,
                3.0,
            )
        except psutil.AccessDenied:
            self._set_taunt(
                "RESISTANCE",
                '"The spirit resists your silver blade."',
                "SHIELDED",
                C_PURPLE,
                4.0,
            )
        except Exception as exc:
            self._set_taunt(
                "HEX FAILED",
                f'"The ritual fizzled: {type(exc).__name__}."',
                "UNSTABLE",
                C_DIM,
                4.0,
            )

    def _resurrect_selected(self) -> None:
        self.crypt.resurrect_latest()

    def _on_resurrect(self, entry: CryptEntry) -> None:
        self._audio.play("collected.wav", 0.45)
        self._set_taunt(
            "SOUL RELEASED",
            f'"The echo of {entry.name} fades from purgatory."',
            "RELEASED",
            C_PURPLE,
            4.0,
        )

    def _toggle_mute(self) -> None:
        self._on_audio_muted(not self._audio.muted)

    def _refresh_audio_status(self) -> None:
        if self._audio.muted:
            self.footer.set_audio_status("AUDIO: SILENCED", C_DIM)
        elif self._audio.available:
            driver = self._audio.driver.upper()
            self.footer.set_audio_status(f"AUDIO: {driver} READY", C_GREEN)
        else:
            self.footer.set_audio_status(
                "AUDIO: DEVICE UNAVAILABLE",
                C_ORANGE,
            )

    def _on_audio_muted(self, muted: bool) -> None:
        self._audio.set_muted(muted)
        self.header.set_muted(muted)
        self._refresh_audio_status()
        if not muted:
            self._audio.play("collected.wav", 0.2)

    def spook(self) -> None:
        self._audio.play("ghost_scream.wav", 0.55)
        self.banner.shake()
        self._swarm.burst(9)
        self._set_taunt(
            "SPOOKED",
            '"BOO! The veil tears for a moment."',
            "STARTLED",
            C_PURPLE,
            3.5,
        )
        self._shake_window()

    def _shake_window(self) -> None:
        origin = self.pos()
        if self._shake_animation is not None:
            self._shake_animation.stop()
        animation = QPropertyAnimation(self, b"pos", self)
        animation.setDuration(380)
        animation.setKeyValueAt(0.0, origin)
        animation.setKeyValueAt(0.15, origin + QPoint(-6, 0))
        animation.setKeyValueAt(0.30, origin + QPoint(6, 0))
        animation.setKeyValueAt(0.45, origin + QPoint(-4, 2))
        animation.setKeyValueAt(0.60, origin + QPoint(4, -2))
        animation.setKeyValueAt(1.0, origin)
        self._shake_animation = animation
        animation.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._decor.setGeometry(self._frame.rect())
        self._swarm.setGeometry(self._frame.rect())
        self._decor.raise_()
        self._swarm.raise_()
        self._flyer.start_patrol()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._decor.setGeometry(self._frame.rect())
        self._swarm.setGeometry(self._frame.rect())
        self._decor.raise_()
        self._swarm.raise_()
        self._flyer.start_patrol()

    def closeEvent(self, event) -> None:
        # Never leave a suspended process behind: release every curse on exit.
        for pid in list(self._cursed_pids):
            try:
                psutil.Process(pid).resume()
            except Exception:
                pass
        self._cursed_pids.clear()

        try:
            self._worker.stop()
        except Exception:
            pass
        try:
            self._whisper_timer.stop()
        except Exception:
            pass
        try:
            self._audio.set_muted(True)
        except Exception:
            pass
        try:
            self._flyer.stop_patrol()
            if getattr(self._flyer, "_movie", None) is not None:
                self._flyer._movie.stop()
        except Exception:
            pass
        try:
            from spookcli.whispers import stop_whispers

            stop_whispers()
        except Exception:
            pass
        super().closeEvent(event)


def run_gtop() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("gtop")
    app.setApplicationDisplayName("gtop")
    icon_path = ASSETS_DIR / "pumpkin.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    font = QFont("Fira Code", 9)
    font.setStyleHint(QFont.StyleHint.Monospace)
    app.setFont(font)
    app.setStyleSheet(
        _style(
            "QToolTip {"
            " color: @TEXT@;"
            " background: @BASE@;"
            " border: 1px solid @BORDER@;"
            " padding: 3px 5px;"
            "}"
            "QScrollBar:vertical {"
            " background: rgba(18, 11, 29, 150);"
            " width: 7px;"
            " margin: 0;"
            " border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical {"
            " background: @BORDER@;"
            " min-height: 22px;"
            " border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical:hover { background: @PURPLE@; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            " background: transparent;"
            "}"
        )
    )
    window = GtopWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_gtop()




