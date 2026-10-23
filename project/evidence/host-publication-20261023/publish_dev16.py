#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bind dev16 identities to the retained exact host publication workflow."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--packet', type=Path, default=Path(__file__).with_name('dev16-publication-packet.json'))
    parser.add_argument('--artifact-directory', type=Path, help='Optional verified downloads supplied by the connected artifact downloader')
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text())
    helper = args.repository_root / 'project/evidence/nondevice-completion-20261023/publish_verified_host.py'
    spec = importlib.util.spec_from_file_location('retained_host_publisher', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Keep the historical dev14 file unchanged; the retained implementation
    # verifies this separately recorded dev16 packet and actual uploaded bytes.
    module.REPO = packet['repository']
    module.SOURCE = packet['source_commit']
    module.INVENTORY = packet['source_inventory_sha256']
    module.RUN = packet['run_id']
    module.RELEASE = packet['release_id']
    module.TAG = packet['tag']
    module.ARTIFACTS = [tuple(item) for item in packet['artifacts']]
    original_gh = module.gh
    artifacts = {f"repos/{module.REPO}/actions/artifacts/{identity}/zip": (identity, expected)
                 for identity, expected in module.ARTIFACTS}
    def gh(*arguments):
        # The connected GitHub artifact downloader supplies these exact bytes.
        # Preserve the retained publisher's independent digest verification.
        if args.artifact_directory is not None and len(arguments) == 2 and arguments[0] == 'api' and arguments[1] in artifacts:
            identity, expected = artifacts[arguments[1]]
            path = args.artifact_directory / (str(identity) + '.zip')
            if path.is_symlink() or not path.is_file():
                raise ValueError('Regular retained artifact required')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Retained artifact checksum differs')
            return raw
        return original_gh(*arguments)
    module.gh = gh
    module.main()


if __name__ == '__main__':
    main()
