#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only installed port/source/readiness/save inventory; never launches."""
import argparse
import json
from pathlib import Path

from psp_shell.ports import PortError, PortsManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sd-root', required=True, type=Path)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    card, output = args.sd_root.resolve(strict=True), args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        parser.error('Write inventory outside the inspected card without symlink traversal')
    output = output.resolve(strict=False)
    if output.is_relative_to(card):
        parser.error('Write inventory outside the inspected card')
    try:
        manager = PortsManager(card)
        report = manager.installed_status(args.port)
        report['save_inventory'] = manager.save_inventory(args.port)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    except (PortError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({'output': str(output), 'port': args.port, 'executed': False, 'runtime_qualified': False}))


if __name__ == '__main__':
    main()
