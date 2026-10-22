# SPDX-License-Identifier: MIT
"""Bounded measurements at an actual presentation call boundary.

These are application call timestamps, not panel scanout or input latency.
An embedded caller must record after its owning Display.present(), never the
embedded Renderer's intentionally empty present method.
"""
from __future__ import annotations

import math

from tools.library_benchmark import distribution


class FrameTimings:
    def __init__(self, maximum=36000, *, boundary='standalone-SDL_RenderPresent-return'):
        if type(maximum) is not int or not 2 <= maximum <= 100000:
            raise ValueError('Frame sample limit must be 2–100000')
        if boundary not in ('standalone-SDL_RenderPresent-return', 'owning-PyUI-Display.present-return'):
            raise ValueError('Select an actual presentation owner boundary')
        self.maximum, self.boundary = maximum, boundary
        self.samples = []
        self.dropped = 0

    def record(self, timestamp_ns, *, render_ns=0, present_ns=0):
        if any(type(value) is not int or value < 0 for value in (timestamp_ns, render_ns, present_ns)):
            raise ValueError('Use nonnegative monotonic integer timestamps/durations')
        if self.samples and timestamp_ns <= self.samples[-1]['timestamp_ns']:
            raise ValueError('Frame timestamps must increase strictly')
        if len(self.samples) >= self.maximum:
            self.dropped += 1
            return
        self.samples.append({'timestamp_ns': timestamp_ns, 'render_ns': render_ns, 'present_ns': present_ns})

    def report(self):
        intervals = [(right['timestamp_ns'] - left['timestamp_ns']) / 1e6
                     for left, right in zip(self.samples, self.samples[1:])]
        return {'schema': 1, 'boundary': self.boundary, 'clock': 'monotonic_ns',
                'samples': self.samples.copy(), 'dropped_samples': self.dropped,
                'interval': distribution(intervals),
                'render_call': distribution([s['render_ns'] / 1e6 for s in self.samples]),
                'present_call': distribution([s['present_ns'] / 1e6 for s in self.samples]),
                'panel_fps': None, 'input_latency_ms': None,
                'limits': ['Intervals include caller work, scheduling and presentation wait.',
                           'A returned present call does not prove display scanout.',
                           'Internal timestamps do not measure physical input latency.']}


def compare_metrics(baseline, candidate, budgets):
    """Apply explicit preselected per-metric ratio/absolute-noise budgets."""
    results = {}
    for name, rule in budgets.items():
        before, after = baseline.get(name), candidate.get(name)
        if not isinstance(rule, dict) or set(rule) != {'ratio', 'noise_ms'}:
            raise ValueError('Each metric needs a ratio and an absolute noise floor')
        ratio, noise = rule['ratio'], rule['noise_ms']
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (ratio, noise)) or ratio < 1 or noise < 0:
            raise ValueError('Invalid comparison budget')
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (before, after)):
            results[name] = {'status': 'unavailable', 'passed': None}
            continue
        limit = max(before * ratio, before + noise)
        results[name] = {'baseline_ms': before, 'candidate_ms': after, 'limit_ms': limit,
                         'passed': after <= limit, 'status': 'measured'}
    return {'metrics': results, 'passed': bool(results) and all(r['passed'] is True for r in results.values())}
