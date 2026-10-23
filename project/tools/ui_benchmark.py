#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure real SDL host presentation with a fixed synthetic navigation scene."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import time

from psp_shell.ui.model import NavigationModel
from psp_shell.ui.renderer import Renderer
from tools.frame_timing import FrameTimings


def capture_frames(output, *, frames=120, warmup=20, software=True):
    if type(frames) is not int or not 2 <= frames <= 36000 or type(warmup) is not int or not 0 <= warmup <= 1000:
        raise ValueError('Use 2–36000 frames and 0–1000 warmup frames')
    model = NavigationModel(demo=True, preferences={'motion': False, 'sounds': False})
    timings = FrameTimings(frames)
    with Renderer(software=software) as renderer:
        for index in range(frames + warmup):
            model.handle('down' if index % 8 < 4 else 'up')
            now = time.monotonic_ns()
            renderer.render(model.snapshot(now / 1e9), now / 1e9)
            rendered = time.monotonic_ns()
            renderer.present()
            presented = time.monotonic_ns()
            if index >= warmup:
                timings.record(presented, render_ns=rendered - now, present_ns=presented - rendered)
    report = {'schema': 1, 'evidence_class': 'synthetic-SDL-host-render',
              'scene': 'demo-home-four-down-four-up-motion-off', 'warmup_frames': warmup,
              'host': {'machine': platform.machine(), 'python': platform.python_version(),
                       'video_driver': os.environ.get('SDL_VIDEODRIVER', 'SDL-selected'), 'software': software},
              'frame_timing': timings.report(), 'hardware_qualified': False,
              'audio_faults': None, 'battery_energy_wh': None,
              'limits': ['No deliberate frame pacing; this is host render-call throughput.',
                         'Not a physical-device game FPS, battery or input-latency benchmark.']}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--warmup', type=int, default=20)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = capture_frames(args.output, frames=args.frames, warmup=args.warmup)
    print(json.dumps(report['frame_timing']['interval']))


if __name__ == '__main__':
    main()
