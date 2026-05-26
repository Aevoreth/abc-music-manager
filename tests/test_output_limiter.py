"""Tests for playback output limiter."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.playback.output_limiter import OutputLimiter


def _make_buffer(values: list[float]) -> memoryview:
    arr = np.array(values, dtype=np.float32)
    return memoryview(arr)


def _read_buffer(buffer: memoryview) -> np.ndarray:
    return np.frombuffer(buffer, dtype=np.float32).copy()


def test_silence_unchanged() -> None:
    limiter = OutputLimiter()
    buf = _make_buffer([0.0, 0.0, -0.0, 0.0])
    limiter.process(buf)
    assert np.allclose(_read_buffer(buf), 0.0)


def test_peak_limiter_caps_hot_signal() -> None:
    limiter = OutputLimiter(ceiling=0.98, soft_clip_drive=1.0)
    buf = _make_buffer([2.0, -2.0, 1.5, -1.5])
    limiter.process(buf)
    out = _read_buffer(buf)
    assert float(np.max(np.abs(out))) <= 0.98 + 1e-6


def test_soft_clip_reduces_hard_peaks_before_limiter() -> None:
    limiter = OutputLimiter(ceiling=1.0, soft_clip_drive=2.0)
    buf = _make_buffer([1.5, -1.5])
    limiter.process(buf)
    out = _read_buffer(buf)
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-6
    assert float(np.max(np.abs(out))) < 1.5


def test_reset_clears_gain_reduction() -> None:
    limiter = OutputLimiter(ceiling=0.5, soft_clip_drive=1.0, release_rate=0.0)
    hot = _make_buffer([4.0, 4.0])
    limiter.process(hot)
    assert limiter._gain < 1.0

    limiter.reset()
    assert limiter._gain == 1.0

    quiet = _make_buffer([0.1, -0.1])
    limiter.process(quiet)
    out = _read_buffer(quiet)
    assert np.allclose(out, [0.1, -0.1], atol=1e-6)


def test_release_smoothes_gain_recovery() -> None:
    limiter = OutputLimiter(ceiling=0.5, soft_clip_drive=1.0, release_rate=0.1)
    limiter.process(_make_buffer([4.0, 4.0]))
    gain_after_loud = limiter._gain

    limiter.process(_make_buffer([0.2, 0.2]))
    assert limiter._gain > gain_after_loud
    assert limiter._gain < 1.0
