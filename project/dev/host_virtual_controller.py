#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Development-only, PID-bound commands for host_virtual_controller.c."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time


def identity(pid: int, executable: Path, sha256: str, expected_start_ticks: int) -> int:
    """Reject reused PIDs and an unexpected executable before publishing input."""
    actual = Path(f"/proc/{pid}/exe").resolve(strict=True)
    if actual != executable.resolve(strict=True):
        raise ValueError("wrong executable")
    with actual.open("rb") as stream:
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
        digest = hasher.hexdigest()
    if digest != sha256:
        raise ValueError("executable digest changed")
    text = Path(f"/proc/{pid}/stat").read_text()
    observed_ticks = int(text[text.rindex(")") + 2:].split()[19])
    if observed_ticks != expected_start_ticks:
        raise ValueError("process start ticks changed")
    return observed_ticks


def private_parent(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("absolute output paths required")
    info = path.parent.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("output parent must be owned and private (0700)")
    if path.is_symlink():
        raise ValueError("output symlink refused")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("existing output must be an owned private regular file")


def send(*, pid: int, expected_start_ticks: int, executable: Path, sha256: str, command: Path, record: Path,
         axes: list[float], buttons: int, seconds: float) -> dict:
    if len(axes) != 4 or any(not math.isfinite(v) or not -1 <= v <= 1 for v in axes):
        raise ValueError("four finite axes in [-1, 1] required")
    if not 0 <= buttons < 32768 or not math.isfinite(seconds) or not .01 <= seconds <= 60:
        raise ValueError("buttons or duration out of range")
    if command.resolve() == record.resolve() or (command.exists() and record.exists() and command.samefile(record)):
        raise ValueError("command and request log must differ")
    private_parent(command)
    private_parent(record)
    ticks = identity(pid, executable, sha256, expected_start_ticks)
    prior = command.read_text().split() if command.exists() else []
    sequence = int(prior[0]) + 1 if prior else 0
    requested = time.monotonic_ns()
    expires = requested + int(seconds * 1e9)
    values = [round(v * 32767) for v in axes]
    payload = " ".join(map(str, [sequence, pid, ticks, requested, expires, *values, buttons])) + "\n"
    temporary = command.with_name(command.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck immediately before the command becomes visible.
        if identity(pid, executable, sha256, expected_start_ticks) != ticks:
            raise ValueError("process changed")
        os.replace(temporary, command)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = dict(sequence=sequence, pid=pid, process_start_ticks=ticks,
                   requested_monotonic_ns=requested, published_monotonic_ns=time.monotonic_ns(),
                   expires_monotonic_ns=expires, axes=values, buttons=buttons,
                   executable_sha256=sha256)
    fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        stream.write(json.dumps(receipt) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-ticks", dest="expected_start_ticks", type=int, required=True,
                        help="process start ticks retained by the launcher")
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--command", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--axes", type=float, nargs=4, default=[0, 0, 0, 0], metavar=("LX", "LY", "RX", "RY"))
    parser.add_argument("--buttons", type=int, default=0, help="SDL button mask: south=1 east=2 west=4 north=8 start=64")
    parser.add_argument("--seconds", type=float, default=.2)
    args = parser.parse_args()
    print(json.dumps(send(**vars(args))))


if __name__ == "__main__":
    main()
