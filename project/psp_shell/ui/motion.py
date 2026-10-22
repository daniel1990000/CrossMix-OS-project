"""Bounded crossbar motion, independent of frame rate and rendering.

The short step/long jump policy follows the design in PlayFieldPortal's
XmbStepMotion.kt at 5ee271ea9545685417aecdd13b5ace033cdb7806.
This is an original Python implementation. SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import math
from typing import Any


class StepGlide:
    """Snap on view changes; glide a row in 100 ms, catching up within 200 ms."""

    def __init__(self) -> None:
        self.identity: Any = None
        self.target = 0.0
        self.origin = 0.0
        self.started = 0.0
        self.duration = 0.0

    def sample(self, now: float) -> float:
        if not self.duration:
            return self.target
        progress = max(0.0, min(1.0, (now - self.started) / self.duration))
        return self.origin + (self.target - self.origin) * progress

    def position(self, target: float, now: float, identity: Any, enabled: bool) -> float:
        if identity != self.identity or not enabled:
            self.identity, self.target, self.origin = identity, target, target
            self.started, self.duration = now, 0.0
        elif target != self.target:
            previous_target = self.target
            self.origin = self.sample(now)
            self.target = target
            if abs(target - previous_target) > 3:
                self.origin = target - math.copysign(1.0, target - previous_target)
            self.duration = min(.2, abs(target - self.origin) * .1)
            self.started = now
        return self.sample(now)
