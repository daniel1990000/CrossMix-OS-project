#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read installed ELF identities and an optional already-running process's maps.

Runs host readelf, never the inspected executable or loader. Absolute symlinks
belong to the inspected filesystem, with /mnt/SDCARD mapped to --sd-root.
Library paths are explicit or observed in maps; no SDK/basename search is used.
This evidence cannot qualify hardware, config writers, saves or a return seam.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import time

from inventory import write_output

MAX_ELF = 128 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
MAX_OBJECTS = 128
CARD = "/mnt/SDCARD"


def absolute_name(value):
    if (not isinstance(value, str) or not value.startswith("/") or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("an absolute installed path without control characters is required")
    return value


class InstalledTree:
    def __init__(self, root, sd_root):
        self.root = Path(root).resolve(strict=True)
        self.card = Path(sd_root).resolve(strict=True)
        if not self.root.is_dir() or not self.card.is_dir():
            raise ValueError("root and SD root must be existing directories")
        self._identities = {base: (base.stat().st_dev, base.stat().st_ino) for base in (self.root, self.card)}

    def host(self, parts):
        if tuple(parts[:2]) == ("mnt", "SDCARD"):
            return self.card.joinpath(*parts[2:])
        return self.root.joinpath(*parts)

    def resolve(self, value):
        pending, parts, links = list(PurePosixPath(absolute_name(value)).parts[1:]), [], 0
        while pending:
            component = pending.pop(0)
            if component == "..":
                if not parts:
                    raise ValueError("installed symlink escapes the filesystem root")
                parts.pop()
                continue
            trial = self.host(parts + [component])
            # The card is an explicit virtual mount, not a host symlink to follow.
            if trial.is_symlink():
                links += 1
                if links > 40:
                    raise ValueError("installed symlink loop")
                target = os.readlink(trial)
                if any(ord(c) < 32 or ord(c) == 127 for c in target):
                    raise ValueError("invalid installed symlink target")
                if target.startswith("/"):
                    parts = []
                pending = list(PurePosixPath(target).parts)[1 if target.startswith("/") else 0:] + pending
            else:
                parts.append(component)
        path = self.host(parts)
        base = self.card if tuple(parts[:2]) == ("mnt", "SDCARD") else self.root
        path.resolve(strict=True).relative_to(base)
        return path

    def _directory(self, path):
        base = self.card if path.is_relative_to(self.card) else self.root
        parts = path.relative_to(base).parts
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self._identities[base]:
                raise ValueError("inspected filesystem root changed")
            for part in parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def open_regular(self, name):
        path = self.resolve(name)
        parent = self._directory(path.parent)
        try:
            return os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)

    def readlink(self, name):
        path = PurePosixPath(absolute_name(name))
        parent = self._directory(self.resolve(str(path.parent)))
        try:
            return os.readlink(path.name, dir_fd=parent)
        finally:
            os.close(parent)

    def text(self, name):
        fd = self.open_regular(name)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("installed metadata must be a regular file")
            data = stream.read(MAX_TEXT + 1)
        if data is None or len(data) > MAX_TEXT:
            raise ValueError("installed metadata exceeds its input budget")
        return data.decode("utf-8", errors="strict")


def symbol_versions(text, section):
    active, owner, result = False, "", {}
    for line in text.splitlines():
        if line.startswith("Version "):
            active = line.startswith("Version " + section + " section")
        if active:
            match = re.search(r"File:\s+(\S+)", line)
            if match:
                owner = match.group(1)
            match = re.search(r"Name:\s+(\S+)", line)
            if match:
                result.setdefault(owner, set()).add(match.group(1))
    return {key: sorted(value) for key, value in result.items()}


def readelf_text(fd, command, timeout=15):
    process = subprocess.Popen([command, "-h", "-l", "-d", "-V", "--wide", "/proc/self/fd/" + str(fd)],
                               pass_fds=(fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=dict(os.environ, LC_ALL="C"))
    deadline, received, output = time.monotonic() + timeout, 0, bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                for key, _ in selector.select(remaining):
                    data = os.read(key.fd, min(65536, MAX_TEXT - received + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    received += len(data)
                    if received > MAX_TEXT:
                        raise ValueError("readelf exceeded its output budget")
                    if key.fileobj is process.stdout:
                        output.extend(data)
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if process.returncode:
            raise ValueError("readelf failed")
        return output.decode("utf-8", errors="strict")
    finally:
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        finally:
            process.stdout.close()
            process.stderr.close()


def inspect_elf(tree, name, readelf="readelf"):
    fd = tree.open_regular(name)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 64 <= before.st_size <= MAX_ELF:
            raise ValueError("ELF must be a bounded regular file")
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ValueError("installed object is not ELF")
            stream.seek(0)
            remaining = before.st_size
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError("installed ELF shrank during hashing")
                digest.update(block)
                remaining -= len(block)
            if stream.read(1):
                raise ValueError("installed ELF grew during hashing")
        # A descriptor keeps inspection and hashing on the same inode. No ldd,
        # executable, loader or shell is invoked, even for untrusted ELF files.
        text = readelf_text(fd, readelf)
        after = os.fstat(fd)
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in keys):
            raise ValueError("installed ELF changed during inspection")
        match = re.search(r"Requesting program interpreter:\s*([^]]+)\]", text)
        soname = re.search(r"\(SONAME\).*?\[([^]]+)\]", text)
        machine = re.search(r"Machine:\s*([^\n]+)", text)
        return {"path": name, "sha256": digest.hexdigest(), "size": before.st_size,
                "machine": machine.group(1).strip() if machine else None,
                "elf64": bool(re.search(r"Class:\s+ELF64\b", text)),
                "interpreter": match.group(1) if match else None,
                "soname": soname.group(1) if soname else None,
                "needed": re.findall(r"\(NEEDED\).*?\[([^]]+)\]", text),
                "search_tags": re.findall(r"\((?:RPATH|RUNPATH)\).*?\[([^]]+)\]", text),
                "required_versions": symbol_versions(text, "needs"),
                "defined_versions": symbol_versions(text, "definition").get("", []),
                "file_identity": {"device": "%x:%x" % (os.major(before.st_dev), os.minor(before.st_dev)),
                                  "inode": before.st_ino}}
    finally:
        os.close(fd)


def process_snapshot(tree, pid):
    if type(pid) is not int or not 0 < pid < 2 ** 31:
        raise ValueError("PID must identify an existing process")
    prefix = "/proc/" + str(pid)
    status = tree.text(prefix + "/stat")
    # comm is parenthesized and may itself contain spaces or parentheses.
    fields = status.rpartition(")")[2].split()
    if not status.startswith(str(pid) + " (") or len(fields) <= 19:
        raise ValueError("process start identity is unavailable")
    starttime = int(fields[19])
    # Read the link value, never resolve /proc/PID/exe on the host for a snapshot.
    executable = absolute_name(tree.readlink(prefix + "/exe"))
    maps = tree.text(prefix + "/maps")
    return {"pid": pid, "starttime_ticks": starttime, "executable": executable,
            "maps_sha256": hashlib.sha256(maps.encode()).hexdigest()}, maps


def mapped_objects(text, executable, interpreter):
    objects, omitted = {}, 0
    for line in text.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6 or not fields[5].startswith("/"):
            continue
        name = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[5])
        # Retain only engine/loader/library identities, never mapped ROM paths.
        library = re.search(r"\.so(?:\.[0-9]+)*$", name)
        allowed = name.startswith(("/lib/", "/lib64/", "/usr/lib/", "/usr/local/lib/",
                                   CARD + "/spruce/", CARD + "/Emu/", CARD + "/App/"))
        if allowed and name.endswith(" (deleted)") and (
                name[:-10] in {executable, interpreter} or re.search(r"\.so(?:\.[0-9]+)*$", name[:-10])):
            raise ValueError("mapped ELF was deleted; current on-disk bytes cannot identify it")
        if name not in {executable, interpreter} and not (library and allowed):
            omitted += 1
            continue
        absolute_name(name)
        identity = {"device": fields[3].lower(), "inode": int(fields[4])}
        if identity["inode"] <= 0 or (name in objects and objects[name] != identity):
            raise ValueError("mapped file has an invalid or changing identity")
        objects[name] = identity
        if len(objects) > MAX_OBJECTS:
            raise ValueError("mapped library inventory exceeds its object budget")
    return objects, omitted


def collect(root, sd_root, executable, libraries=(), pid=None, readelf="readelf"):
    tree = InstalledTree(root, sd_root)
    absolute_name(executable)
    if not executable.startswith(CARD + "/Emu/"):
        raise ValueError("select an installed emulator path under /mnt/SDCARD/Emu/")
    explicit = set(libraries)
    if len(explicit) > MAX_OBJECTS:
        raise ValueError("too many explicit library paths")
    for name in explicit:
        absolute_name(name)
    records, errors = {}, []

    def inspect(name):
        if name in records:
            return
        try:
            records[name] = inspect_elf(tree, name, readelf)
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append({"path": name, "reason": "ELF unavailable, changed or unreadable"})

    inspect(executable)
    interpreter = records.get(executable, {}).get("interpreter")
    if interpreter:
        absolute_name(interpreter)
        inspect(interpreter)
    else:
        errors.append({"path": executable, "reason": "dynamic interpreter unavailable"})
    snapshot, maps, observed, omitted = None, None, {}, 0
    if pid is not None:
        snapshot, maps = process_snapshot(tree, pid)
        observed, omitted = mapped_objects(maps, executable, interpreter)
        if snapshot["executable"] != executable or executable not in observed:
            raise ValueError("PID does not identify the selected mapped executable")
    if len(explicit | set(observed) | {executable, interpreter}) > MAX_OBJECTS:
        raise ValueError("combined library inventory exceeds its object budget")
    for name in sorted(explicit | set(observed)):
        inspect(name)
    live = tree.root == Path("/") and tree.card == Path(CARD).resolve()
    stable = None
    if snapshot is not None:
        after, _ = process_snapshot(tree, pid)
        stable = after == snapshot
        for name, identity in observed.items():
            if name in records:
                actual = records[name]["file_identity"]
                normalized_device = ":".join(format(int(x, 16), "x") for x in identity["device"].split(":"))
                matched = actual == dict(identity, device=normalized_device)
                records[name]["mapped_inode_matches"] = matched if live else None
                if live and not matched:
                    errors.append({"path": name, "reason": "on-disk object differs from mapped inode"})
        if not stable:
            errors.append({"path": "/proc/" + str(pid), "reason": "process identity or mappings changed during collection"})
    for name, record in records.items():
        if record["machine"] != "AArch64" or not record["elf64"]:
            errors.append({"path": name, "reason": "object is not AArch64 ELF64"})
    # Keep every matching identity. Ambiguity is an error, never an arbitrary
    # alphabetical selection that could mistake SDK contents for loaded files.
    dependency_checks = []
    for name, record in sorted(records.items()):
        for needed in sorted(set(record["needed"]) | set(record["required_versions"])):
            candidates = [r for p, r in records.items() if p != executable
                          and (r["soname"] == needed or PurePosixPath(p).name == needed)]
            check = {"requester": name, "library": needed,
                     "candidates": [r["path"] for r in candidates], "missing_versions": []}
            if len(candidates) != 1:
                check["status"] = "missing" if not candidates else "ambiguous"
            else:
                check["missing_versions"] = sorted(set(record["required_versions"].get(needed, []))
                                                   - set(candidates[0]["defined_versions"]))
                check["status"] = "missing_versions" if check["missing_versions"] else "present_in_supplied_objects"
            dependency_checks.append(check)
    return {"schema": 1, "kind": "read-only-installed-runtime", "target_executed": False,
            "live_root": live, "process_identity": snapshot, "process_stable": stable,
            "omitted_nonlibrary_mappings": omitted, "objects": list(records.values()),
            "errors": errors, "dependency_checks": dependency_checks,
            "physical_qualification": False, "resume_qualified": False,
            "limits": ["No loader search order is inferred; only explicit and observed mapped paths are inspected.",
                       "Snapshot inode numbers cannot be compared with copied host files.",
                       "Process mappings and on-disk identities do not prove graphics behavior or memory contents.",
                       "Config writers, input, save completion, surviving children and foreground return require separate evidence."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--sd-root", type=Path, default=Path(CARD))
    parser.add_argument("--executable", default=CARD + "/Emu/PSP/PPSSPPSDL_TrimUI")
    parser.add_argument("--library", action="append", default=[])
    parser.add_argument("--pid", type=int)
    parser.add_argument("--readelf", default="readelf")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = collect(args.root, args.sd_root, args.executable, args.library, args.pid, args.readelf)
        write_output(args.output, report, args.sd_root)
        print(str(args.output))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("installed-runtime: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
