#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bind hold decisions to every changed upstream path, including outside scopes.

Reads Git metadata, never source code. This is a coverage/identity check for an
engineering decision to keep current pins; it cannot approve an update or device.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from dev.certify import source_specs
from tools.upstream_drift import SCOPES, SHA1, _git, in_scope, publish

ZERO = '0' * 40
MAX_CHANGES = 100000
GROUP_ID = re.compile(r'[a-z][a-z0-9-]{0,79}\Z')


def _object(mode, object_id):
    if mode == '000000' and object_id == ZERO:
        return None
    if mode not in {'100644', '100755', '120000', '160000'} or not SHA1.fullmatch(object_id) or object_id == ZERO:
        raise ValueError('Invalid changed object mode or identity')
    return {'mode': mode, 'kind': 'commit' if mode == '160000' else 'blob', 'git_object': object_id}


def changes(root, baseline, candidate):
    """Read the complete raw delta without materializing large unchanged trees."""
    for commit in (baseline, candidate):
        if not isinstance(commit, str) or not SHA1.fullmatch(commit):
            raise ValueError('Review requires exact commit identities')
        if _git(root, 'rev-parse', '--verify', commit + '^{commit}').decode().strip() != commit:
            raise ValueError('Expected exact commit object')
    raw = _git(root, 'diff-tree', '--no-commit-id', '--no-renames', '--no-ext-diff',
               '--no-textconv', '--raw', '-r', '-z', baseline, candidate)
    fields = raw.split(b'\0')
    if fields[-1] != b'' or (len(fields) - 1) % 2:
        raise ValueError('Malformed changed-path metadata')
    records = []
    seen = set()
    for offset in range(0, len(fields) - 1, 2):
        if len(records) >= MAX_CHANGES:
            raise ValueError('Changed-path count exceeds review bound')
        metadata = fields[offset].decode('ascii').split()
        if len(metadata) != 5 or not metadata[0].startswith(':') or metadata[4] not in {'A', 'D', 'M', 'T'}:
            raise ValueError('Unsupported changed-path metadata')
        path = fields[offset + 1].decode('utf-8')
        if (not path or path.startswith('/') or len(path) > 2048 or path in seen or
                any(part in ('', '.', '..') for part in path.split('/'))):
            raise ValueError('Invalid or duplicate changed path')
        seen.add(path)
        before = _object(metadata[0][1:], metadata[2])
        after = _object(metadata[1], metadata[3])
        if before == after:
            raise ValueError('Delta contains an unchanged object')
        records.append({'path': path, 'before': before, 'after': after})
    return sorted(records, key=lambda record: record['path'])


def validate(source, baseline, candidate, inventory, decision):
    """Require one exact, explained hold for every changed path in both scopes."""
    if source not in SCOPES or decision.get('schema') != 1:
        raise ValueError('Unknown source or review schema')
    if any(decision.get(key) != value for key, value in
           [('source', source), ('baseline_commit', baseline), ('candidate_commit', candidate)]):
        raise ValueError('Review source or commit identities differ')
    groups = decision.get('groups')
    entries = decision.get('paths')
    if not isinstance(groups, list) or not isinstance(entries, list):
        raise ValueError('Review groups and paths must be lists')
    group_map = {}
    for group in groups:
        if not isinstance(group, dict) or not GROUP_ID.fullmatch(group.get('id', '')) or group['id'] in group_map:
            raise ValueError('Invalid or duplicate review group')
        if (group.get('decision') != 'hold-current-pin' or
                not isinstance(group.get('reason'), str) or len(group['reason'].strip()) < 20 or
                not isinstance(group.get('required_before_adoption'), list) or
                not group['required_before_adoption'] or
                any(not isinstance(item, str) or not item.strip() for item in group['required_before_adoption'])):
            raise ValueError('Review must explain a hold and prerequisites')
        group_map[group['id']] = group
    expected = {record['path']: record for record in inventory}
    if len(expected) != len(inventory):
        raise ValueError('Duplicate inventory path')
    reviewed = {}
    counts = collections.Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid review entry')
        path = entry.get('path')
        if not isinstance(path, str) or path in reviewed or path not in expected:
            raise ValueError('Review has duplicate or unexpected path')
        if any(entry.get(key) != expected[path][key] for key in ('before', 'after')):
            raise ValueError('Review changed-object identity differs')
        if entry.get('group') not in group_map:
            raise ValueError('Review path lacks a valid decision group')
        reviewed[path] = entry
        counts[entry['group']] += 1
    if set(reviewed) != set(expected):
        raise ValueError('Review omits changed paths, including outside scope')
    return {'schema': 1, 'kind': 'upstream-hold-review-validation', 'source': source,
            'baseline_commit': baseline, 'candidate_commit': candidate,
            'changed_paths': len(inventory),
            'changed_in_scope': sum(in_scope(path, SCOPES[source]) for path in expected),
            'changed_outside_scope': sum(not in_scope(path, SCOPES[source]) for path in expected),
            'decision_groups': dict(sorted(counts.items())), 'all_changed_paths_bound_to_hold': True,
            'review_coverage': 'metadata identity and explained hold; no full behavioral audit or adoption',
            'pins_updated': False, 'candidate_executed': False, 'device_qualified': False,
            'adoption_authorized': False, 'distribution_cleared': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, choices=sorted(SCOPES))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--review', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        baseline = next(item[2] for item in source_specs() if item[0] == args.source)
        raw = Path(args.review).read_bytes()
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('Review packet exceeds size bound')
        packet = json.loads(raw)
        if not isinstance(packet, dict):
            raise ValueError('Review packet must be an object')
        inventory = changes(args.repository, baseline, args.candidate)
        report = validate(args.source, baseline, args.candidate, inventory, packet)
        report['review_sha256'] = hashlib.sha256(raw).hexdigest()
        # A second metadata read catches input mutation rather than trusting an earlier list.
        if changes(args.repository, baseline, args.candidate) != inventory:
            raise ValueError('Changed-path metadata changed during review')
        receipt = publish(args.output, report, [args.repository])
        print(json.dumps({**receipt, 'changed_paths': len(inventory), 'adoption_authorized': False}))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('maintenance: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
