#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Write a local JSON support bundle from selected copies; never upload anything."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).absolute().parent))
from inventory import redact, SECRET_WORDS

MAX_FILE = 128 * 1024


def sanitize(value, depth=0):
    if depth > 16:
        return "[DEPTH LIMIT]"
    if isinstance(value, dict):
        private_fields = {"before", "after", "backup", "snapshot", "content_base64", "data_base64",
                          "raw", "raw_bytes", "value", "values", "original_record", "provenance"}
        return {str(k): "[REDACTED]" if SECRET_WORDS.search(str(k)) or str(k).casefold() in private_fields else sanitize(v, depth + 1)
                for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(x, depth + 1) for x in value[:2048]]
    if isinstance(value, str):
        value = redact(value)
        value = re.sub(r"(?:/mnt/SDCARD/)?(?:Roms|Saves)/[^\s\"']+", "[USER DATA PATH]", value)
        return value[:4096]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[UNSUPPORTED VALUE]"


def export(inventory, diagnostics, output):
    paths = [Path(inventory), *map(Path, diagnostics)]
    if len(paths) > 8:
        raise ValueError("at most seven selected diagnostics")
    entries = []
    for index, path in enumerate(paths):
        if {part.casefold() for part in path.absolute().parts} & {"transactions", "previews", "migrations"} or \
                path.name.casefold().endswith((".backup", ".bak")) or path.name.casefold() == "journal.json":
            raise ValueError("configuration snapshots/backups/journals must not enter support bundles")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError("selected evidence must be a bounded regular JSON/text file")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        try:
            data = sanitize(json.loads(text))
        except (ValueError, RecursionError):
            data = sanitize(text)
        # Do not publish source filenames or hashes of secret/raw input contents.
        entries.append({"role": "inventory" if index == 0 else "selected-diagnostic",
                        "data": data})
    result = {"schema": 1, "kind": "local-redacted-support", "automatic_upload": False,
              "review_before_sharing": True, "entries": entries}
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists")
    raw = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {"output": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "uploaded": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--diagnostic", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export(args.inventory, args.diagnostic, args.output), indent=2))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("support: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
