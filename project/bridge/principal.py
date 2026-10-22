"""Principal's fixed child-process boundary; never a power or emulator owner.

The helper runs the existing source launcher/command. Linux child-subreaper
adoption retains double-forked/setsid descendants. It observes every child exit
until ECHILD; it never kills a surviving game to make another UI start. Kernel
exit closes the owned processes' input/display descriptors and Python threads.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile
import uuid

from .bootstrap import ForegroundIdentity, PRINCIPAL_PATH, SpruceReturnEvidence
from .process_source import (COMMAND_REQUEST, ProcessSourceConfiguration,
                             SourceCommandRequest, configured_runtime, process_start)
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError, SPRUCE_COMMIT


PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37
MAX_COMMAND = 1024 * 1024
DISABLED = 64
BLOCKED = 125
_KERNEL_SEAL = object()


@dataclass(frozen=True)
class OwnedTreeCompletion:
    root_pid: int
    exit_status: int
    children_reaped: int
    _seal: object


def _subreaper(value=None):
    libc = ctypes.CDLL(None, use_errno=True)
    current = ctypes.c_int()
    if libc.prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(current), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Linux child-subreaper observation is unavailable")
    if value is not None and libc.prctl(PR_SET_CHILD_SUBREAPER, int(value), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Linux child-subreaper activation is unavailable")
    return current.value


def run_owned_tree(argv, *, pass_fds=(), env=None) -> OwnedTreeCompletion:
    """Run one fixed trusted source operation in this dedicated helper.

    Call only in principal's fresh helper process. Existing children are
    refused; a live descendant keeps this wait pending, even after the staged
    shell exits. No process names, argv, ROM paths or environment are exported.
    """
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise ContractError("FOREIGN_CHILD", "The principal helper already owns another child")
    previous = _subreaper(True)
    root, reaped, root_status, complete = None, 0, None, False
    try:
        root = subprocess.Popen(argv, pass_fds=tuple(pass_fds), close_fds=True, env=env)
        while True:
            try:
                pid, status = os.waitpid(-1, 0)
            except InterruptedError:
                continue
            except ChildProcessError:
                complete = True
                break
            reaped += 1
            if pid == root.pid:
                root_status = os.waitstatus_to_exitcode(status)
                root.returncode = root_status
        if root_status is None:
            raise ContractError("RETURN_UNVERIFIED", "The kernel did not report the launched root process exit")
        return OwnedTreeCompletion(root.pid, root_status, reaped, _KERNEL_SEAL)
    finally:
        # Restoring subreaper state is safe only once there are no descendants.
        # Signals/termination provide no completion object or foreground clear.
        if root is None or complete:
            _subreaper(previous)


@dataclass(frozen=True)
class PrincipalCompletion:
    foreground: ForegroundIdentity
    principal_sha256: str
    tree: OwnedTreeCompletion
    verification_id: str
    _seal: object

    def spruce_return(self) -> SpruceReturnEvidence:
        if (self._seal is not _KERNEL_SEAL or type(self.tree) is not OwnedTreeCompletion or
                self.tree._seal is not _KERNEL_SEAL or self.tree.children_reaped < 1):
            raise ContractError("RETURN_UNVERIFIED", "Only the actual kernel-owned process boundary can issue a return")
        return SpruceReturnEvidence(self.foreground, SPRUCE_COMMIT, self.principal_sha256,
                                    True, True, self.verification_id)


def _bounded_command(fd):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_COMMAND:
        raise ContractError("STAGED_COMMAND_INVALID", "The existing staged command must be a bounded regular file")
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while len(raw) <= before.st_size:
        block = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
        if not block:
            break
        raw.extend(block)
    after = os.fstat(fd)
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if len(raw) != before.st_size or any(getattr(before, k) != getattr(after, k) for k in keys):
        raise ContractError("STAGED_COMMAND_CHANGED", "The existing staged command changed while being captured")
    return bytes(raw), tuple(getattr(before, k) for k in keys)


def _create_memfd():
    flags = getattr(os, "MFD_CLOEXEC", 0x0001) | getattr(os, "MFD_ALLOW_SEALING", 0x0002)
    function = getattr(os, "memfd_create", None)
    if callable(function):
        return function("spruce-staged-command", flags)
    # Linux UAPI: asm-generic/unistd.h (__NR_memfd_create=279) and
    # x86/asm/unistd_64.h (=319). This supports the original older-glibc
    # Python build without introducing a replacement libc or loader.
    numbers = {"aarch64": 279, "arm64": 279, "x86_64": 319, "amd64": 319}
    number = numbers.get(platform.machine().lower()) if sys.platform.startswith("linux") else None
    if number is None:
        raise ContractError("SOURCE_CAPABILITY_UNAVAILABLE", "The qualified principal has no reviewed memfd syscall for this architecture")
    libc = ctypes.CDLL(None, use_errno=True)
    syscall = libc.syscall
    syscall.restype = ctypes.c_long
    descriptor = syscall(number, ctypes.c_char_p(b"spruce-staged-command"), ctypes.c_uint(flags))
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "Linux sealed command descriptor creation is unavailable")
    return descriptor


def _sealed_script(raw):
    fd = _create_memfd()
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            view = view[count:]
        os.lseek(fd, 0, os.SEEK_SET)
        # Linux UAPI asm-generic/fcntl.h + linux/fcntl.h. Some Python builds
        # omit these exported names while their kernel supports memfd seals.
        add_seals, get_seals = getattr(fcntl, "F_ADD_SEALS", 1033), getattr(fcntl, "F_GET_SEALS", 1034)
        required = 0x0001 | 0x0002 | 0x0004 | 0x0008
        fcntl.fcntl(fd, add_seals, required)
        if fcntl.fcntl(fd, get_seals) & required != required:
            raise ContractError("SOURCE_CAPABILITY_UNAVAILABLE", "The principal command descriptor could not be sealed")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _parent_identity():
    pid = os.getppid()
    start = process_start(pid)
    if start is None:
        raise ContractError("RETURN_UNVERIFIED", "The existing principal process is unavailable")
    return pid, start


def _consume_staged(path, expected_raw, expected_identity):
    """Atomically take the object, then verify it in a private directory.

    A replacement is restored with no-replace linking when the source name is
    still absent. If another object appeared there, retain both objects and
    refuse completion. Never unlink an unchecked pathname after comparing it.
    """
    quarantine = Path(tempfile.mkdtemp(prefix=".spruce-consume-", dir=path.parent))
    captured = quarantine / "command"
    moved, verified = False, False
    try:
        os.rename(path, captured)
        moved = True
        descriptor = os.open(captured, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            raw, identity = _bounded_command(descriptor)
        finally:
            os.close(descriptor)
        # rename updates ctime; device/inode/size/mtime and exact bytes must
        # still identify the object originally captured for execution.
        if identity[:4] != expected_identity[:4] or hashlib.sha256(raw).digest() != hashlib.sha256(expected_raw).digest():
            raise ContractError("STAGED_COMMAND_CHANGED", "Principal captured a replacement staged command")
        verified = True
        os.unlink(captured)
        quarantine.rmdir()
    except BaseException:
        if moved and not verified:
            try:
                os.link(captured, path, follow_symlinks=False)
            except OSError:
                # Preserve the captured replacement in its private quarantine
                # when another staged object now owns the original name.
                pass
            else:
                os.unlink(captured)
                quarantine.rmdir()
        elif not moved:
            quarantine.rmdir()
        raise


class PrincipalBoundary:
    def __init__(self, config: ProcessSourceConfiguration):
        if type(config) is not ProcessSourceConfiguration:
            raise ContractError("INVALID_CONTEXT", "Principal requires the fixed reviewed typed source configuration")
        self.config = config
        self.health = FrontendHealth(config.state_dir)

    def run_pyui(self):
        self.config.assert_safe()
        self.health.assert_no_foreground()
        if os.path.lexists(self.config.staged_command):
            raise ContractError("FOREGROUND_UNCERTAIN", "Principal must consume the existing staged command before another UI")
        parent = _parent_identity()
        from .resident import PrincipalLease, CAPABILITY_ENV, SERVER_ENV, source_environment
        lease = PrincipalLease(self.config)
        lease.begin_source()
        environment = dict(os.environ)
        for key in ("TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE", CAPABILITY_ENV):
            environment.pop(key, None)
        # Only the source subtree receives a live relay capability. A host
        # fixture without any resident-mutating UI may omit the service.
        if SERVER_ENV in environment:
            environment.update(source_environment(self.config))
        elif self.config.execution_environment != "host-fixture":
            raise ContractError("RESIDENT_UNVERIFIED", "Qualified source routes require principal's resident delegation authority")
        result = run_owned_tree([str(self.config.sd_root / "App/PyUI/launch.sh")], env=environment)
        self.config.assert_safe()
        if _parent_identity() != parent:
            raise ContractError("RETURN_UNVERIFIED", "The existing principal changed during its source process boundary")
        lease.close_source(result)
        return result

    def run_command(self) -> tuple[OwnedTreeCompletion, PrincipalCompletion | None]:
        self.config.assert_safe()
        parent = _parent_identity()
        expected = ForegroundIdentity.from_health(self.health)
        if expected is not None and expected.boot_id != self.health.boot_id:
            raise ContractError("RETURN_UNVERIFIED", "A cross-boot foreground cannot supply a current principal return")
        request = SourceCommandRequest.read(self.config) if expected is not None else None
        if request is not None and (request.foreground != expected or
                process_start(request.source_pid) == request.source_start):
            raise ContractError("RETURN_UNVERIFIED", "Source identity mismatched or its process still owns the session")
        path = self.config.staged_command
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            raw, identity = _bounded_command(descriptor)
        finally:
            os.close(descriptor)
        if request is not None and request.command_sha256 != hashlib.sha256(raw).hexdigest():
            raise ContractError("STAGED_COMMAND_CHANGED", "The staged command differs from the actual source handoff request")
        from .resident import PrincipalLease, CAPABILITY_ENV, SERVER_ENV
        lease = PrincipalLease(self.config)
        lease.consume_source(expected, request, hashlib.sha256(raw).hexdigest())
        environment = dict(os.environ)
        for key in ("TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE", CAPABILITY_ENV, SERVER_ENV):
            environment.pop(key, None)
        if self.config.command_environment is not None and expected is not None:
            scoped = self.config.command_environment(expected, request)
            if (not isinstance(scoped, dict) or set(scoped) - {"TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE"} or
                    any(not isinstance(v, str) or len(v) > 4096 or any(ord(c) < 32 for c in v) for v in scoped.values()) or
                    any(v and not v.startswith("/") for v in scoped.values())):
                raise ContractError("INVALID_STATE_ENVIRONMENT", "Only fixed bounded private state-session fields may accompany the existing command")
            environment.update(scoped)
        sealed = _sealed_script(raw)
        try:
            # Preserve the original staged script's $0 without executing a
            # mutable pathname. No extra positional arguments are introduced.
            result = run_owned_tree(["/bin/sh", "-c", ". /proc/self/fd/%d" % sealed, str(path)],
                                    pass_fds=(sealed,), env=environment)
        finally:
            os.close(sealed)
        self.config.assert_safe()
        if _parent_identity() != parent or ForegroundIdentity.from_health(self.health) != expected:
            raise ContractError("STALE_HANDOFF", "Principal or exact foreground identity changed during command execution")
        _consume_staged(path, raw, identity)
        if os.path.lexists(path):
            raise ContractError("FOREGROUND_UNCERTAIN", "Another staged command appeared before source return")
        completion = None
        if expected is not None:
            completion = PrincipalCompletion(expected, self.config.profile["required_hashes"][PRINCIPAL_PATH],
                result, "principal:" + uuid.uuid4().hex, _KERNEL_SEAL)
            completion.spruce_return()
            if self.config.completion_observer is not None:
                self.config.completion_observer(completion)
            self.config.assert_safe()
            if os.path.lexists(path) or ForegroundIdentity.from_health(self.health) != expected:
                raise ContractError("STALE_HANDOFF", "Foreground or staging changed while collecting principal completion")
            self.health.clear_foreground(expected.token, verified=True, expected_generation=expected.generation)
            os.unlink(self.config.state_dir / COMMAND_REQUEST)
        lease.complete_command(result)
        return result, completion


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "pyui", "command", "resident", "resident-ready"))
    parser.add_argument("server_pid", nargs="?", type=int)
    args = parser.parse_args(argv)
    try:
        config = configured_runtime()
        if config is None:
            # Even a disabled integration cannot start classic over a retained
            # same-boot project handoff. No metadata supplies executable code.
            from .resident import DIRTY_GUARD
            if os.path.lexists(DIRTY_GUARD):
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "A boot-global source/process boundary remains incomplete")
            FrontendHealth("/mnt/SDCARD/App/PSPMode/state").assert_no_foreground()
            return DISABLED
        config.assert_safe()
        if args.operation == "status":
            from .resident import PrincipalLease
            PrincipalLease(config).assert_clean()
            previous = _subreaper(True)
            _subreaper(previous)
            descriptor = _sealed_script(b":\n")
            os.close(descriptor)
            return 0
        boundary = PrincipalBoundary(config)
        if args.operation == "resident":
            from .resident import ResidentServer
            ResidentServer(config).serve()
        elif args.operation == "resident-ready":
            from .resident import wait_ready
            wait_ready(config, args.server_pid)
        elif args.operation == "pyui":
            boundary.run_pyui()
        else:
            boundary.run_command()
        # This is ownership completion, not emulator/save success. A nonzero
        # original command status still permits a verified resource return.
        return 0
    except (OSError, ValueError, ContractError, subprocess.SubprocessError) as exc:
        print("principal boundary blocked: " + getattr(exc, "code", "SOURCE_OPERATION_FAILED"), file=sys.stderr)
        return BLOCKED


if __name__ == "__main__":
    sys.exit(main())
