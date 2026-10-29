#!/usr/bin/env python3
"""Bounded synthetic SDL queue integration probe; no games or device adapter."""
import ctypes
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sdl2
from psp_shell import app
from psp_shell.ui.renderer import Renderer

scenario, output = sys.argv[1], Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
buttons = {name: getattr(sdl2, 'SDL_CONTROLLER_BUTTON_' + name) for name in
           ('DPAD_RIGHT', 'DPAD_DOWN', 'A', 'B')}
# Each action is sent only once its preceding observable state arrives.
if scenario == 'settings':
    steps = [
        ('home', lambda s: s.category == 0, 'DPAD_RIGHT'),
        ('continue', lambda s: s.category == 1, 'DPAD_RIGHT'),
        ('tools', lambda s: s.category == 2, 'DPAD_RIGHT'),
        ('settings', lambda s: s.category == 3 and s.selected_item.title == 'Confirm button', 'A'),
        ('settings preview', lambda s: s.dialog is not None and s.dialog.title == 'Change confirm button', 'A'),
        ('settings applied', lambda s: s.dialog is None and s.preferences.confirm == 'east' and 'updated' in s.status.lower(), 'B'),
        ('east confirm opens preview', lambda s: s.dialog is not None and s.dialog.title == 'Change confirm button', 'A'),
        ('south cancel returns', lambda s: s.dialog is None and s.preferences.confirm == 'east', None),
    ]
elif scenario == 'launch':
    steps = [
        ('home', lambda s: s.title == 'Your games', 'A'),
        ('library', lambda s: s.title == 'All games' and s.selected_item is not None, 'A'),
        ('game card', lambda s: s.dialog is not None and s.dialog.title == 'Alpine Rally', 'A'),
        ('preview refusal', lambda s: s.dialog is not None and s.dialog.title == 'Sample collection' and 'never starts games' in s.dialog.message, 'A'),
        ('return to library', lambda s: s.title == 'All games' and s.dialog is None, 'B'),
        ('return home', lambda s: s.title == 'Your games', None),
    ]
else:
    raise SystemExit('unknown scenario')

original = Renderer.render
seen = []
index = 0
started = time.monotonic()
last_action = 0.0

def render(self, snapshot, now=0):
    global index, last_action
    original(self, snapshot, now)
    if index < len(steps) and time.monotonic() - started > 15:
        raise RuntimeError('timeout waiting for ' + steps[index][0])
    if index < len(steps) and time.monotonic() - last_action >= .04:
        label, predicate, button = steps[index]
        if predicate(snapshot):
            seen.append({'step': label, 'title': snapshot.title,
                         'selection': snapshot.selected_item.title if snapshot.selected_item else None,
                         'dialog': snapshot.dialog.title if snapshot.dialog else None,
                         'confirm': snapshot.preferences.confirm, 'status': snapshot.status})
            if label in ('settings applied', 'preview refusal', 'return home'):
                self.save_screenshot(str(output / (scenario + '-' + label.replace(' ', '-') + '.png')))
            index += 1
            if button is None:
                event = sdl2.SDL_Event()
                event.type = sdl2.SDL_QUIT
                if sdl2.SDL_PushEvent(ctypes.byref(event)) != 1:
                    raise RuntimeError('SDL push quit failed')
            if button:
                event = sdl2.SDL_Event()
                event.type = sdl2.SDL_CONTROLLERBUTTONDOWN
                event.cbutton.which = 17
                event.cbutton.button = buttons[button]
                if sdl2.SDL_PushEvent(ctypes.byref(event)) != 1:
                    raise RuntimeError('SDL push down failed')
                event.type = sdl2.SDL_CONTROLLERBUTTONUP
                if sdl2.SDL_PushEvent(ctypes.byref(event)) != 1:
                    raise RuntimeError('SDL push up failed')
                last_action = time.monotonic()
    time.sleep(.005)  # Allow asynchronous dispatcher completions in dummy video mode.

Renderer.render = render
with tempfile.TemporaryDirectory(prefix='trimui-controller-fixture-') as state:
    result = app.main(['--demo', '--headless', '--width', '1280', '--height', '720',
                       '--frames', '1000', '--state-dir', state])
if result or index != len(steps):
    raise SystemExit('scenario failed: exit=%s completed=%d/%d' % (result, index, len(steps)))
(output / (scenario + '.json')).write_text(json.dumps({'scenario': scenario, 'steps': seen,
    'result': 'pass', 'input': 'synthetic SDL_CONTROLLERBUTTONDOWN/UP through SDL queue',
    'backend': 'DemoBackend', 'real_game_launches': 0, 'device_test': False}, indent=2) + '\n')
