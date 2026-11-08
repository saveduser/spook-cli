"""gtop logic and offscreen UI smoke tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections import deque

import pytest

pytest.importorskip("PyQt6")

from spookcli import gtop  # noqa: E402


def test_haunted_port_mapping_and_squatter_flag() -> None:
    row = gtop.ProcessRow(pid=42, name="node", cpu=1.0, mem=2.0, status="running", ports=[3000, 9999])
    assert row.haunted_ports == [3000]
    assert row.squatter is True

    quiet = gtop.ProcessRow(pid=43, name="sleep", cpu=0.0, mem=0.1, status="sleeping", ports=[9999])
    assert quiet.haunted_ports == []
    assert quiet.squatter is False


def test_rss_history_prunes_dead_pids() -> None:
    history: dict[int, deque[float]] = {
        1: deque([1.0], maxlen=gtop.LEAK_WINDOW),
        2: deque([2.0], maxlen=gtop.LEAK_WINDOW),
    }
    rows = [gtop.ProcessRow(pid=2, name="alive", cpu=0.0, mem=0.0, status="sleeping", rss_mb=8.0)]

    gtop._update_rss_history(rows, history)

    assert 1 not in history
    assert list(history[2]) == [2.0, 8.0]


def test_detect_leak_prefers_steadily_growing_process(monkeypatch) -> None:
    monkeypatch.setattr(gtop.os, "getpid", lambda: 999)
    grower = gtop.ProcessRow(pid=10, name="leaky", cpu=1.0, mem=1.0, status="running", rss_mb=100.0)
    hog = gtop.ProcessRow(pid=11, name="hog", cpu=1.0, mem=1.0, status="running", rss_mb=900.0)
    history = {
        10: deque([100.0, 108.0, 120.0], maxlen=gtop.LEAK_WINDOW),
        11: deque([900.0, 900.0, 900.0], maxlen=gtop.LEAK_WINDOW),
    }

    pid, growth = gtop._detect_leak([grower, hog], history)

    assert pid == 10
    assert growth == pytest.approx(20.0)


def test_detect_leak_falls_back_to_largest_resident(monkeypatch) -> None:
    monkeypatch.setattr(gtop.os, "getpid", lambda: 999)
    rows = [
        gtop.ProcessRow(pid=10, name="small", cpu=0.0, mem=0.0, status="sleeping", rss_mb=10.0),
        gtop.ProcessRow(pid=11, name="big", cpu=0.0, mem=0.0, status="sleeping", rss_mb=800.0),
    ]

    pid, growth = gtop._detect_leak(rows, {})

    assert pid == 11
    assert growth == 0.0


def test_detect_leak_ignores_own_process(monkeypatch) -> None:
    monkeypatch.setattr(gtop.os, "getpid", lambda: 11)
    rows = [gtop.ProcessRow(pid=11, name="gtop", cpu=0.0, mem=0.0, status="running", rss_mb=900.0)]

    assert gtop._detect_leak(rows, {}) == (None, 0.0)


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_window_builds_offscreen(qapp) -> None:
    window = gtop.GtopWindow()
    try:
        assert window.windowTitle() == "gtop — Haunted Process Monitor"
        assert (window.width(), window.height()) == (480, 820)
        sheet = window._frame.styleSheet()
        assert "rgba(15, 20, 28, 180)" in sheet
        assert window._cursed_pids == set()
    finally:
        window.close()
