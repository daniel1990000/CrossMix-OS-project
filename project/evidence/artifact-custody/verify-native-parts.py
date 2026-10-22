#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Hash ordered retrieved parts; never extract, load, install or execute them."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat


def verify(manifest, artifact_id, paths):
    record = json.loads(Path(manifest).read_bytes())
    matches = [a for a in record["artifacts"] if a["id"] == artifact_id]
    if len(matches) != 1:
        raise ValueError("one recorded artifact required")
    artifact = matches[0]
    if len(paths) != len(artifact["parts"]):
        raise ValueError("supply every part in recorded order")
    combined, size = hashlib.sha256(), 0
    for order, (expected, path) in enumerate(zip(artifact["parts"], paths)):
        path = Path(path)
        if path.is_symlink() or not 0 < expected["size_bytes"] <= 64 * 1024**2:
            raise ValueError("bounded regular part required")
        if expected["order"] != order:
            raise ValueError("invalid recorded part order")
        part = hashlib.sha256()
        with path.open("rb") as stream:
            info = stream.fileno()
            if not stat.S_ISREG(os.fstat(info).st_mode):
                raise ValueError("part must be a regular file")
            remaining = expected["size_bytes"]
            while remaining:
                block = stream.read(min(1024**2, remaining))
                if not block:
                    raise ValueError("short retrieved part")
                part.update(block)
                combined.update(block)
                remaining -= len(block)
                size += len(block)
            if stream.read(1) or part.hexdigest() != expected["sha256"]:
                raise ValueError("retrieved part hash/size differs")
    if size != artifact["size_bytes"] or combined.hexdigest() != artifact["sha256"]:
        raise ValueError("reassembled archive hash/size differs")
    return {"artifact": artifact_id, "sha256": combined.hexdigest(), "size_bytes": size,
            "parts_verified": len(paths), "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "hardware_qualified": False, "source_use_verified": False, "production_authorization": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("parts", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.manifest, args.artifact, args.parts), indent=2))
