# SPDX-License-Identifier: MIT
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PortInventoryCliTests(unittest.TestCase):
    def test_readonly_cli_writes_outside_the_card_without_creating_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            card = root / 'card'
            card.mkdir()
            output = root / 'inventory.json'
            script = Path(__file__).resolve().parents[1] / 'tools/port_inventory.py'
            process = subprocess.run([sys.executable, str(script), '--sd-root', str(card),
                '--port', 'sonic_mania', '--output', str(output)], capture_output=True, text=True,
                env=dict(os.environ, PYTHONPATH=str(script.parents[1])), timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertFalse(json.loads(output.read_text())['executed'])
            self.assertEqual(list(card.iterdir()), [])

    def test_output_on_card_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            card = Path(temporary)
            script = Path(__file__).resolve().parents[1] / 'tools/port_inventory.py'
            process = subprocess.run([sys.executable, str(script), '--sd-root', str(card),
                '--port', 'sonic_mania', '--output', str(card / 'report.json')], capture_output=True, text=True,
                env=dict(os.environ, PYTHONPATH=str(script.parents[1])), timeout=5)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(list(card.iterdir()), [])

    def test_parent_components_cannot_hide_an_output_on_the_card(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            card, sibling = root / 'card', root / 'sibling'
            card.mkdir()
            sibling.mkdir()
            script = Path(__file__).resolve().parents[1] / 'tools/port_inventory.py'
            output = sibling / '..' / 'card' / 'report.json'
            process = subprocess.run([sys.executable, str(script), '--sd-root', str(card),
                '--port', 'sonic_mania', '--output', str(output)], capture_output=True, text=True,
                env=dict(os.environ, PYTHONPATH=str(script.parents[1])), timeout=5)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(list(card.iterdir()), [])
