"""Stereo output limiter: tanh soft clip plus block peak limiting."""

from __future__ import annotations

import numpy as np

# Just below full scale; avoids hard float clipping at ±1.0.
_DEFAULT_CEILING = 0.95
# >1.0 bends peaks gently before the peak limiter acts.
_DEFAULT_SOFT_CLIP_DRIVE = 2.0
# Per-buffer gain recovery toward unity (0–1, higher = slower release).
_DEFAULT_RELEASE_RATE = 0.05


class OutputLimiter:
    """
    In-place processor for stereo interleaved float32 audio buffers.

    Applies normalized tanh soft clipping, then a simple peak limiter with
    instant attack and smoothed release so gain reduction does not click
    between PyAudio callbacks.
    """

    __slots__ = ("_ceiling", "_drive", "_release_rate", "_tanh_drive", "_gain")

    def __init__(
        self,
        *,
        ceiling: float = _DEFAULT_CEILING,
        soft_clip_drive: float = _DEFAULT_SOFT_CLIP_DRIVE,
        release_rate: float = _DEFAULT_RELEASE_RATE,
    ) -> None:
        self._ceiling = float(ceiling)
        self._drive = float(soft_clip_drive)
        self._release_rate = float(release_rate)
        self._tanh_drive = np.tanh(self._drive)
        self._gain = 1.0

    def reset(self) -> None:
        """Clear envelope state (call when starting or stopping playback)."""
        self._gain = 1.0

    def process(self, buffer: memoryview) -> None:
        """Process a stereo interleaved float32 buffer in place."""
        samples = np.frombuffer(buffer, dtype=np.float32)
        if samples.size == 0:
            return

        if self._drive != 1.0:
            scaled = samples * self._drive
            np.tanh(scaled, out=samples)
            samples /= self._tanh_drive

        peak = float(np.max(np.abs(samples)))
        if peak > 1e-12:
            target_gain = min(1.0, self._ceiling / peak)
        else:
            target_gain = 1.0

        if target_gain < self._gain:
            self._gain = target_gain
        elif target_gain > self._gain:
            self._gain += (target_gain - self._gain) * self._release_rate

        if self._gain != 1.0:
            samples *= self._gain
