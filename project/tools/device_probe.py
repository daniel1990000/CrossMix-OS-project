#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded D03 observations; neither this report nor a helper admits a device.

Offline roots are read only. Only explicit live collection can execute the
trusted --version tools or the disposable kernel helper. It starts no game,
hardware service, input owner, candidate, mount or firmware operation.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid

# Descriptor-executed kernel helpers use only the standard library. This
# avoids resolving project imports from /proc/self/fd or mutable tool paths.
if sys.argv[1:] != ["--kernel-helper"]:
    from installed_runtime import InstalledTree
    from inventory import redact
    from recovery_preflight import directory_fd, write_report

MAX_TEXT = 64 * 1024
MAX_TOOL = 128 * 1024 * 1024
MAX_OUTPUT = 16 * 1024
IDENTITY_KEYS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def read_text(tree, name, limit=MAX_TEXT):
    """Read one fixed metadata file through the anchored inspected root."""
    fd = tree.open_regular(name)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("metadata is not a regular file")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(raw) > limit or any(getattr(before, key) != getattr(after, key) for key in IDENTITY_KEYS):
            raise ValueError("metadata changed or exceeded its byte budget")
    return raw.decode("utf-8", errors="strict")


def _optional(tree, name):
    try:
        return read_text(tree, name)
    except (OSError, ValueError, UnicodeError):
        return None


def process_identity(tree, pid):
    if type(pid) is not int or not 0 < pid < 2**31:
        raise ValueError("an existing positive PID is required")
    text = read_text(tree, "/proc/%d/stat" % pid, 32768)
    fields = text.rpartition(")")[2].split()
    if (not text.startswith(str(pid) + " (") or len(fields) <= 19 or
            fields[0] in {"Z", "X"} or not fields[19].isdigit()):
        raise ValueError("stable live process start identity unavailable")
    return {"pid": pid, "starttime_ticks": int(fields[19])}


def boot_identity(tree):
    value = read_text(tree, "/proc/sys/kernel/random/boot_id", 128).strip()
    if str(uuid.UUID(value)) != value.lower():
        raise ValueError("boot identity is malformed")
    return value.lower()


def run_bounded(argv, *, pass_fds=(), timeout=3, limit=MAX_OUTPUT):
    """Kill only this disposable subprocess group on timeout/output overflow."""
    process = subprocess.Popen(argv, pass_fds=tuple(pass_fds), close_fds=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                               start_new_session=True)
    deadline, received, stdout = time.monotonic() + timeout, 0, bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("disposable observation exceeded its deadline")
                for key, _ in selector.select(remaining):
                    block = os.read(key.fd, min(4096, limit - received + 1))
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    received += len(block)
                    if received > limit:
                        raise ValueError("disposable observation exceeded its output budget")
                    if key.fileobj is process.stdout:
                        stdout.extend(block)
        # Observe root exit without reaping it. A trusted tool/helper can fork
        # and close both pipes before its disposable children have finished;
        # pipe EOF and root success therefore do not establish cleanup. Keeping
        # the root unreaped reserves its PID while its group is stopped, so the
        # cleanup signal cannot target a reused process-group identity.
        while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("disposable observation exceeded its deadline after closing output")
            time.sleep(min(.01, remaining))
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=1)
        if process.returncode:
            raise ValueError("disposable observation failed")
        return bytes(stdout)
    finally:
        try:
            # This group was created by this Popen, with only disposable probe
            # children. Never signal an observed PID, game, service or helper.
            # returncode is assigned only by wait(); before that the root is
            # still this process's unreaped child, so its PID cannot be reused.
            # Never signal the group after normal/nonzero root reaping.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
        finally:
            process.stdout.close()
            process.stderr.close()


def tool_identity(tree, name, *, execute_version=False):
    if execute_version and tree.root != Path("/"):
        raise ValueError("offline inspected tools must never execute")
    fd = tree.open_regular(name)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_TOOL:
            raise ValueError("tool is not a bounded regular file")
        digest, total = hashlib.sha256(), 0
        while total <= before.st_size:
            block = os.read(fd, min(65536, before.st_size + 1 - total))
            if not block:
                break
            digest.update(block)
            total += len(block)
        if total != before.st_size:
            raise ValueError("tool changed while hashing")
        version = None
        if execute_version:
            version = redact(run_bounded(["/proc/self/fd/" + str(fd), "--version"],
                                         pass_fds=(fd,)).decode("utf-8", errors="strict").strip())[:512]
        after = os.fstat(fd)
        if any(getattr(before, key) != getattr(after, key) for key in IDENTITY_KEYS):
            raise ValueError("tool changed during observation")
        current_fd = tree.open_regular(name)
        try:
            current = os.fstat(current_fd)
            if any(getattr(before, key) != getattr(current, key) for key in IDENTITY_KEYS):
                raise ValueError("tool path changed during observation")
        finally:
            os.close(current_fd)
        return {"path": redact(name), "sha256": digest.hexdigest(), "bytes": total,
                "version": version, "version_executed": execute_version}
    finally:
        os.close(fd)


def _wait(pid):
    observed, status = os.waitpid(pid, 0)
    if observed != pid or not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise ValueError("disposable child failed")


def kernel_helper():
    """Runs only in a new short-lived process; changes its own process state."""
    result = {}
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "child subreaper unsupported")
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(read_fd)
            grandchild = os.fork()
            if grandchild == 0:
                os.close(write_fd)
                time.sleep(.025)
                os._exit(0)
            os.write(write_fd, str(grandchild).encode("ascii"))
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        grandchild = int(os.read(read_fd, 32))
        os.close(read_fd)
        _wait(child)
        _wait(grandchild)
        if libc.prctl(36, previous.value, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "child subreaper restore failed")
        result["subreaper_adoption_wait"] = "supported"
    except (OSError, ValueError, AttributeError) as exc:
        result["subreaper_adoption_wait"] = "unavailable:" + type(exc).__name__
    try:
        fd = os.memfd_create("trimui-d03-probe", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
        try:
            os.write(fd, b"bounded-probe")
            # Match principal's Linux UAPI fallback when Python omits the
            # exported names. Unsupported kernel operations still fail here.
            seals = 0x0001 | 0x0002 | 0x0004 | 0x0008
            add_seals, get_seals = getattr(fcntl, "F_ADD_SEALS", 1033), getattr(fcntl, "F_GET_SEALS", 1034)
            fcntl.fcntl(fd, add_seals, seals)
            if fcntl.fcntl(fd, get_seals) & seals != seals:
                raise ValueError("memfd seals incomplete")
            child = os.fork()
            if child == 0:
                try:
                    # The production principal passes a sealed descriptor
                    # across exec, so fork inheritance alone is insufficient.
                    os.set_inheritable(fd, True)
                    program = ("import os,sys,errno\nfd=int(sys.argv[1])\n"
                               "os.lseek(fd,0,os.SEEK_SET)\n"
                               "if os.read(fd,32)!=b'bounded-probe': sys.exit(2)\n"
                               "try: os.write(fd,b'bad')\n"
                               "except OSError as exc: sys.exit(0 if exc.errno==errno.EPERM else 3)\n"
                               "sys.exit(4)\n")
                    os.execv(sys.executable, [sys.executable, "-c", program, str(fd)])
                except BaseException:
                    os._exit(5)
            _wait(child)
            result["sealed_memfd_inherited_read"] = "supported"
        finally:
            os.close(fd)
    except (OSError, ValueError, AttributeError) as exc:
        result["sealed_memfd_inherited_read"] = "unavailable:" + type(exc).__name__
    try:
        with tempfile.TemporaryDirectory(prefix="trimui-d03-peer-") as temporary:
            address = str(Path(temporary) / "peer")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.settimeout(1)
                server.bind(address)
                server.listen(1)
                child = os.fork()
                if child == 0:
                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                            client.connect(address)
                            client.sendall(b"probe")
                        os._exit(0)
                    except BaseException:
                        os._exit(2)
                with server.accept()[0] as peer:
                    peer_pid, uid, gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                _wait(child)
                if (peer_pid, uid, gid) != (child, os.getuid(), os.getgid()):
                    raise ValueError("peer identity mismatch")
                result["unix_peer_credentials"] = "supported"
    except (OSError, ValueError, AttributeError) as exc:
        result["unix_peer_credentials"] = "unavailable:" + type(exc).__name__
    return result


def _opened_helper_input(path, limit):
    """Pin the actual interpreter/source inode before the helper starts."""
    canonical = Path(path).resolve(strict=True)
    parent = directory_fd(canonical.parent)
    try:
        fd = os.open(canonical.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        identity, information = _helper_input_identity(fd, canonical, limit)
        return fd, canonical, identity, information
    except BaseException:
        os.close(fd)
        raise


def _helper_input_identity(fd, canonical, limit):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
        raise ValueError("helper input is not a bounded regular file")
    digest, offset = hashlib.sha256(), 0
    while offset <= before.st_size:
        block = os.pread(fd, min(65536, before.st_size + 1 - offset), offset)
        if not block:
            break
        digest.update(block)
        offset += len(block)
    after = os.fstat(fd)
    if offset != before.st_size or any(getattr(before, key) != getattr(after, key) for key in IDENTITY_KEYS):
        raise ValueError("helper input changed during hashing")
    return tuple(getattr(before, key) for key in IDENTITY_KEYS), {
        "path": redact(str(canonical)), "sha256": digest.hexdigest(), "bytes": offset}


def observe_kernel():
    interpreter = _opened_helper_input(sys.executable, MAX_TOOL)
    try:
        source = _opened_helper_input(__file__, MAX_TEXT)
        try:
            raw = run_bounded(["/proc/self/fd/" + str(interpreter[0]),
                               "/proc/self/fd/" + str(source[0]), "--kernel-helper"],
                              pass_fds=(interpreter[0], source[0]), timeout=5)
            value = json.loads(raw)
            names = {"subreaper_adoption_wait", "sealed_memfd_inherited_read", "unix_peer_credentials"}
            if not isinstance(value, dict) or set(value) != names or any(
                    not isinstance(item, str) or (item != "supported" and not re.fullmatch(r"unavailable:[A-Za-z]+", item))
                    for item in value.values()):
                raise ValueError("kernel helper returned an invalid bounded observation")
            for pinned, limit in ((interpreter, MAX_TOOL), (source, MAX_TEXT)):
                current = _helper_input_identity(pinned[0], pinned[1], limit)
                if current != (pinned[2], pinned[3]):
                    raise ValueError("executed helper input changed during observation")
                # Bind the reported pathname as well as the actual executed fd.
                check = _opened_helper_input(pinned[1], limit)
                try:
                    if check[2:] != pinned[2:]:
                        raise ValueError("executed helper input path changed during observation")
                finally:
                    os.close(check[0])
            return {"capabilities": value, "interpreter": interpreter[3], "source": source[3],
                    "execution": "hashed opened interpreter and source descriptors; standard-library-only helper"}
        finally:
            os.close(source[0])
    finally:
        os.close(interpreter[0])


def collect(root, sd_root, *, pid=None, python_path="/usr/bin/python3", readelf_path="/usr/bin/readelf",
            kernel_probe=False, tool_versions=False):
    tree = InstalledTree(root, sd_root)
    live = tree.root == Path("/")
    if (kernel_probe or tool_versions) and not live:
        raise ValueError("offline roots cannot execute tools or produce kernel observations")
    errors = []
    def observed(name, operation):
        try:
            return operation()
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append({"observation": name, "reason": type(exc).__name__})
            return None
    boot = observed("boot_identity", lambda: boot_identity(tree))
    process = observed("process_identity", lambda: process_identity(tree, pid)) if pid is not None else None
    models = {}
    for name in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        text = _optional(tree, name)
        if text is not None:
            models[name] = redact(text.replace("\x00", " ").strip())[:256]
    cpu = _optional(tree, "/proc/cpuinfo")
    if cpu:
        hardware = re.search(r"(?im)^Hardware\s*:\s*([^\r\n]+)$", cpu)
        if hardware:
            models["/proc/cpuinfo:Hardware"] = redact(hardware.group(1))[:256]
    model_text = " ".join(models.values()).casefold()
    target = "original-tg5040-candidate" if ("tg5040" in model_text or "smart pro" in model_text) and not re.search(
        r"\bbrick\b|smart\s+pro\s+s\b", model_text) else None
    firmware = []
    for name in ("/etc/version", "/etc/trimui_version", "/etc/firmware_version", "/usr/trimui/etc/version.txt"):
        text = _optional(tree, name)
        match = re.search(r"\b1\.\d+\.\d+\b", text) if text else None
        if match:
            firmware.append({"path": name, "version": match.group(0)})
    mounts = []
    text = _optional(tree, "/proc/mounts") or ""
    for line in text.splitlines()[:4096]:
        fields = line.split()
        if len(fields) >= 4 and fields[1] in {"/", "/mnt/SDCARD"} and re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", fields[2]):
            mounts.append({"mountpoint": fields[1], "filesystem": fields[2],
                           "flags": sorted(set(fields[3].split(",")) & {"ro", "rw", "noexec", "nosuid", "nodev", "sync"})})
    kernel_release = _optional(tree, "/proc/sys/kernel/osrelease")
    if kernel_release is not None:
        kernel_release = kernel_release.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", kernel_release):
            kernel_release = None
    tools = {}
    for label, name in (("python", python_path), ("readelf", readelf_path)):
        tools[label] = observed("tool:" + label, lambda name=name: tool_identity(tree, name, execute_version=tool_versions))
    kernel = observed("kernel_helper", observe_kernel) if kernel_probe else None
    # Snapshot again after tool reads/helper execution. No PID reuse, boot
    # transition or dead process can be silently labelled a stable observation.
    if boot is not None and observed("boot_identity_after", lambda: boot_identity(tree)) != boot:
        errors.append({"observation": "boot_identity", "reason": "changed_during_collection"})
        boot = None
    if process is not None and observed("process_identity_after", lambda: process_identity(tree, pid)) != process:
        errors.append({"observation": "process_identity", "reason": "changed_during_collection"})
        process = None
    return {"schema": 1, "kind": "d03-read-only-observation", "live_collector_root": live,
            "provenance": "live collector host" if live else "copied filesystem metadata; not target live evidence",
            "model_observations": models, "model_candidate": target, "firmware_observations": firmware,
            "boot_id": boot, "process_identity": process, "filesystems": mounts, "tools": tools,
            "kernel_release": kernel_release, "collector_architecture": os.uname().machine if live else None,
            "kernel_helper": kernel, "kernel_helper_provenance": "fresh disposable collector-host helper" if kernel is not None else "not_run",
            "errors": errors, "hardware_qualified": False, "runtime_verified": False,
            "physical_restore_tested": False, "automatic_activation": False,
            "limitations": ["Model labels and copied metadata require operator review; no physical device is authenticated.",
                            "Helper results describe this collector kernel only; no display/input/save/recovery test ran.",
                            "Versions execute only the explicitly supplied trusted live tools; offline tools never execute.",
                            "No complete writer inventory, source-use decision or production admission is established."]}


def main(argv=None):
    if argv is None and sys.argv[1:] == ["--kernel-helper"]:
        print(json.dumps(kernel_helper(), sort_keys=True))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--sd-root", type=Path, required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--python", default="/usr/bin/python3")
    parser.add_argument("--readelf", default="/usr/bin/readelf")
    parser.add_argument("--kernel-probe", action="store_true", help="opt-in: disposable helper on the live collector only")
    parser.add_argument("--tool-versions", action="store_true", help="execute only explicit trusted live --version tools")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = collect(args.root, args.sd_root, pid=args.pid, python_path=args.python,
                         readelf_path=args.readelf, kernel_probe=args.kernel_probe, tool_versions=args.tool_versions)
        root = Path(args.root).resolve(strict=True)
        roots = [Path(args.sd_root).resolve(strict=True)] + ([root] if root != Path("/") else [Path("/proc"), Path("/sys"), Path("/etc")])
        write_report(args.output, report, roots)
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print("device probe refused: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
