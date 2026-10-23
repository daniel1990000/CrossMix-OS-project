"""Private principal lifetime and delegation to existing shared shell services.

The relay is principal's child, outside each foreground subtree. It owns and
reaps descendants of the unchanged Bluetooth/WiFi/network/inputd authorities;
it neither claims they stopped nor implements another hardware controller.
Private HMAC capabilities are volatile data, never executable configuration.
"""
from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import subprocess
import time

from .bootstrap import ForegroundIdentity
from .process_source import SourceCommandRequest, process_start
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError


CAPABILITY_ENV = "TRIMUI_PROJECT_RESIDENT_CAPABILITY"
SERVER_ENV = "TRIMUI_PROJECT_RESIDENT_SERVER"
DIRTY_GUARD = Path("/tmp/trimui-project-principal/dirty")
MAX_MESSAGE = 8192
SERVICES = {"samba", "ssh", "syncthing", "sftpgo", "raproxy"}
SCRIPT_PREFIX = "/mnt/SDCARD/spruce/scripts/"
NETWORK_TOGGLE = SCRIPT_PREFIX + "applySetting/networkServiceToggle.sh"
TASKS = {SCRIPT_PREFIX + "tasks/clearwifi.sh", SCRIPT_PREFIX + "tasks/updateRAOfflineProxy.sh"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _mac(key, value):
    return hmac.new(key, _canonical(value), hashlib.sha256).hexdigest()


def _private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ContractError("RESIDENT_UNVERIFIED", "The private principal directory cannot follow symlinks")
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ContractError("RESIDENT_UNVERIFIED", "The private principal directory has another owner or permissions")


def _read_private(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_MESSAGE):
            raise ContractError("RESIDENT_UNVERIFIED", "The principal capability is not a bounded private regular file")
        raw = os.read(descriptor, MAX_MESSAGE + 1)
        if len(raw) != info.st_size:
            raise ContractError("RESIDENT_UNVERIFIED", "The private principal capability changed")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ContractError("RESIDENT_UNVERIFIED", "The private principal record must be an object")
        return value
    finally:
        os.close(descriptor)


def _write_private(path, value):
    raw = _canonical(value)
    if len(raw) > MAX_MESSAGE:
        raise ContractError("RESIDENT_UNVERIFIED", "The private principal record exceeded its bound")
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(8))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _private_key(path, identity):
    try:
        key = _read_private(path)
    except FileNotFoundError:
        key = {**identity, "key": secrets.token_hex(32)}
        temporary = path.with_name(".key." + secrets.token_hex(8))
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(descriptor, _canonical(key))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            key = _read_private(path)
        finally:
            temporary.unlink()
    if (any(key.get(k) != v for k, v in identity.items()) or not isinstance(key.get("key"), str) or
            len(key["key"]) != 64):
        raise ContractError("RESIDENT_UNVERIFIED", "Private principal capability belongs to another boot or process")
    return bytes.fromhex(key["key"])


def _lineage(pid, ancestor, start):
    """Observe a bounded live lineage, including the ancestor start identity."""
    for _ in range(64):
        if pid == ancestor:
            return process_start(pid) == start
        try:
            with open("/proc/%d/stat" % pid, "rb") as source:
                raw = source.read(32769)
            fields = raw.rpartition(b")")[2].split()
            if len(raw) > 32768 or len(fields) < 2 or fields[0] in {b"Z", b"X"}:
                return False
            parent = int(fields[1])
            if parent <= 1 or parent == pid:
                return False
            pid = parent
        except (OSError, ValueError):
            return False
    return False


class PrincipalLease:
    """Boot/principal-bound source closure; absence/dead PID is never proof."""

    def __init__(self, config, principal=None):
        self.config = config
        self.principal = principal or (os.getppid(), process_start(os.getppid()))
        if self.principal[1] is None:
            raise ContractError("RESIDENT_UNVERIFIED", "The existing principal identity is unavailable")
        _private_directory(config.private_runtime)
        self.directory = config.private_runtime / ("%d-%s" % self.principal)
        _private_directory(self.directory)
        self.identity = {"principal_pid": self.principal[0], "principal_start": self.principal[1],
                         "boot_id": FrontendHealth(config.state_dir).boot_id}
        self.key = _private_key(self.directory / "key.json", self.identity)
        self.boot_key = _private_key(config.private_runtime / "boot-key.json", {"boot_id": self.identity["boot_id"]})

    @contextmanager
    def transaction(self):
        descriptor = os.open(self.config.private_runtime / "authority.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ContractError("RESIDENT_UNVERIFIED", "The principal ownership lock is not private")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def global_state(self):
        try:
            value = _read_private(self.config.private_runtime / "lifetime.json")
        except FileNotFoundError:
            value = {"phase": "idle", "boot_id": self.identity["boot_id"]}
        else:
            signature = value.pop("mac", None)
            if (not isinstance(signature, str) or not hmac.compare_digest(signature, _mac(self.boot_key, value)) or
                    value.get("boot_id") != self.identity["boot_id"]):
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "The boot-global ownership record did not authenticate")
        dirty = os.path.lexists(self.config.private_runtime / "dirty")
        if value.get("phase") not in {"idle", "source-running", "source-closed", "command-running"} or dirty != (value.get("phase") != "idle"):
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "The boot-global owner transition is incomplete")
        if value["phase"] != "idle" and any(value.get(k) != self.identity[k] for k in ("principal_pid", "principal_start")):
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "A previous principal lifetime still owns an incomplete boundary")
        return value

    def set_global(self, phase):
        guard = self.config.private_runtime / "dirty"
        if phase != "idle":
            try:
                descriptor = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        value = {**self.identity, "phase": phase}
        _write_private(self.config.private_runtime / "lifetime.json", {**value, "mac": _mac(self.boot_key, value)})
        if phase == "idle":
            guard.unlink(missing_ok=True)

    def assert_clean(self):
        with self.transaction():
            if self.global_state()["phase"] != "idle":
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "A foreground ownership boundary remains incomplete")

    def read(self, name):
        value = _read_private(self.directory / name)
        signature = value.pop("mac", None)
        if not isinstance(signature, str) or not hmac.compare_digest(signature, _mac(self.key, value)):
            raise ContractError("RESIDENT_UNVERIFIED", "The private principal record authentication failed")
        if any(value.get(k) != v for k, v in self.identity.items()):
            raise ContractError("RESIDENT_UNVERIFIED", "The private principal record belongs to another lifetime")
        return value

    def write(self, name, value):
        value = {**value, **self.identity}
        _write_private(self.directory / name, {**value, "mac": _mac(self.key, value)})

    def begin_source(self, *, experimental_session=None):
        with self.transaction():
            if self.global_state()["phase"] != "idle":
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "An earlier source or command boundary remains active")
            if experimental_session is not None:
                from .experimental_runtime import ExperimentalRuntimeSession
                if type(experimental_session) is not ExperimentalRuntimeSession:
                    raise ContractError("EXPERIMENTAL_REJECTED", "The source admission is not the fixed reviewed typed session")
                name = experimental_session.record_name
                if not isinstance(name, str) or not re.fullmatch(r"experimental-[0-9a-f]{64}\.json", name):
                    raise ContractError("EXPERIMENTAL_REJECTED", "The experimental case identity is invalid")
                try:
                    self.read(name)
                except FileNotFoundError:
                    pass
                else:
                    raise ContractError("EXPERIMENTAL_REPLAY", "This boot/principal case has already been reserved or consumed")
                now = time.monotonic()
                self.write(name, {"phase": "prepared", "candidate_sha256": experimental_session.candidate_sha256,
                    "case_sha256": experimental_session.case_sha256, "helper_pid": os.getpid(),
                    "helper_start": process_start(os.getpid()), "started_monotonic": now,
                    "view_deadline": now + experimental_session.view_seconds,
                    "return_deadline": now + experimental_session.view_seconds + experimental_session.return_seconds})
            self._begin_source()
            if experimental_session is not None:
                current = self.read(experimental_session.record_name)
                self.write(experimental_session.record_name, {**current, "source_nonce": self.read("source.json")["nonce"]})

    def _begin_source(self):
        try:
            prior = self.read("source.json")
        except FileNotFoundError:
            prior = None
        if prior is not None and prior.get("phase") not in {"closed-empty", "complete"}:
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "An earlier source/command boundary remains incomplete")
        self.set_global("source-running")
        self.write("source.json", {"phase": "running", "helper_pid": os.getpid(),
                                  "helper_start": process_start(os.getpid()), "nonce": secrets.token_hex(32)})

    def close_source(self, completion):
        with self.transaction():
            if self.global_state()["phase"] != "source-running":
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "This principal no longer owns a running source boundary")
            self._close_source(completion)

    def _close_source(self, completion):
        from .principal import OwnedTreeCompletion, _KERNEL_SEAL
        if type(completion) is not OwnedTreeCompletion or completion._seal is not _KERNEL_SEAL:
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Only actual source subtree completion closes its private boundary")
        current = self.read("source.json")
        if (current.get("phase") != "running" or current.get("helper_pid") != os.getpid() or
                current.get("helper_start") != process_start(os.getpid())):
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Source helper no longer owns its private boundary")
        foreground = ForegroundIdentity.from_health(FrontendHealth(self.config.state_dir))
        request = SourceCommandRequest.read(self.config) if foreground is not None else None
        if request is not None and request.foreground != foreground:
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Source request no longer matches its pending foreground")
        digest = None
        if os.path.lexists(self.config.staged_command):
            from .principal import _bounded_command
            descriptor = os.open(self.config.staged_command, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                raw, _ = _bounded_command(descriptor)
                digest = hashlib.sha256(raw).hexdigest()
            finally:
                os.close(descriptor)
        if request is not None and request.command_sha256 != digest:
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Source staged command changed before subtree completion")
        self.write("source.json", {**current, "phase": "closed" if digest else "closed-empty",
            "command_sha256": digest, "foreground": asdict(foreground) if foreground else None,
            "request_sha256": hashlib.sha256(_canonical(asdict(request))).hexdigest() if request else None})
        self.set_global("source-closed" if digest else "idle")

    def consume_source(self, foreground, request, digest):
        with self.transaction():
            lifetime = self.global_state()
            if lifetime["phase"] not in {"idle", "source-closed"}:
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Another source or command still owns the foreground boundary")
            self._consume_source(foreground, request, digest, lifetime["phase"])

    def _consume_source(self, foreground, request, digest, lifetime_phase):
        try:
            current = self.read("source.json")
        except FileNotFoundError:
            # Original boot-staged classic commands precede any source process.
            # A project tombstone can never take this original-source path.
            if foreground is not None or lifetime_phase != "idle":
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "No actual source subtree completion exists for this foreground")
            current = {}
        else:
            if (lifetime_phase != "source-closed" or current.get("phase") != "closed" or current.get("command_sha256") != digest or
                    current.get("foreground") != (asdict(foreground) if foreground else None) or
                    current.get("request_sha256") != (hashlib.sha256(_canonical(asdict(request))).hexdigest() if request else None)):
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "The exact authenticated source closure is absent or already consumed")
        # Commit before launch: killing the command helper cannot replay a
        # previous source closure over descendants that may still be alive.
        self.set_global("command-running")
        self.write("source.json", {**current, "phase": "command-running", "command_sha256": digest,
            "command_helper_pid": os.getpid(), "command_helper_start": process_start(os.getpid())})

    def complete_command(self, completion):
        from .principal import OwnedTreeCompletion, _KERNEL_SEAL
        if type(completion) is not OwnedTreeCompletion or completion._seal is not _KERNEL_SEAL:
            raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "Only actual command subtree completion closes the global lifetime")
        with self.transaction():
            current = self.read("source.json")
            if (self.global_state()["phase"] != "command-running" or current.get("phase") != "command-running" or
                    current.get("command_helper_pid") != os.getpid() or current.get("command_helper_start") != process_start(os.getpid())):
                raise ContractError("SOURCE_CLOSURE_UNVERIFIED", "The command no longer owns its global boundary")
            self.write("source.json", {**current, "phase": "complete"})
            self.set_global("idle")


def _peer(connection):
    return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))


def _receive(connection):
    raw = bytearray()
    while len(raw) <= MAX_MESSAGE:
        block = connection.recv(min(1024, MAX_MESSAGE + 1 - len(raw)))
        if not block:
            break
        raw.extend(block)
        if raw.endswith(b"\n"):
            break
    if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
        raise ContractError("INVALID_RESIDENT_REQUEST", "The resident request is incomplete or too large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ContractError("INVALID_RESIDENT_REQUEST", "The resident message must be an object")
    return value


def _send(connection, value):
    raw = _canonical(value) + b"\n"
    if len(raw) > MAX_MESSAGE:
        raise ContractError("INVALID_RESIDENT_REQUEST", "The resident response exceeded its bound")
    connection.sendall(raw)


def operation_argv(config, operation, arguments):
    """Data never chooses a program: map exact fixed operation shapes."""
    if not isinstance(arguments, list) or any(not isinstance(v, str) for v in arguments):
        raise ContractError("INVALID_RESIDENT_REQUEST", "Resident arguments must be bounded typed data")
    scripts = config.sd_root / "spruce/scripts"
    if operation == "bluetooth-apply" and arguments == []:
        return ["/bin/sh", str(scripts / "bluetooth.sh"), "apply"]
    if operation == "wifi" and len(arguments) == 1 and arguments[0] in {"apply", "restart", "suspend", "connect", "forget-all"}:
        return ["/bin/sh", str(scripts / "wifi.sh"), arguments[0]]
    if operation == "input-calibration" and arguments == []:
        return ["/bin/sh", "-c", ". " + str(scripts / "helperFunctions.sh") + " && restart_trimui_inputd"]
    if operation == "network-service" and len(arguments) == 2 and arguments[0] in SERVICES and arguments[1] in {"True", "False"}:
        return ["/bin/sh", str(scripts / "applySetting/networkServiceToggle.sh"), *arguments]
    if operation == "task" and len(arguments) == 1 and arguments[0] in {"clearwifi.sh", "updateRAOfflineProxy.sh"}:
        return ["/bin/sh", str(scripts / "tasks" / arguments[0])]
    raise ContractError("INVALID_RESIDENT_REQUEST", "This command has no reviewed resident delegation")


class ResidentServer:
    def __init__(self, config):
        self.config, self.lease = config, PrincipalLease(config)
        self.scopes = {}
        self.reaped = 0
        self.closing = False

    def _experimental(self, value, scope, peer_pid):
        """Observe one admitted source through the existing authenticated relay.

        The caller already checked peer credentials, live ancestry, MAC and the
        consumed sequence. A message can name only a phase, never a callback,
        candidate, principal, key, executable or authority record.
        """
        session = getattr(self.config, "experimental_session", None)
        if session is None or value.get("stdin") is not None or value.get("arguments") not in (["startup"], ["view"], ["return-start"], ["return"]):
            raise ContractError("EXPERIMENTAL_REJECTED", "The view-only relay request is unavailable or has an invalid phase")
        phase = value["arguments"][0]
        with self.lease.transaction():
            if self.lease.global_state()["phase"] != "source-running":
                raise ContractError("EXPERIMENTAL_REJECTED", "The experimental source no longer owns its running lifetime")
            record = self.lease.read(session.record_name)
            source = self.lease.read("source.json")
            if (record.get("candidate_sha256") != session.candidate_sha256 or
                    record.get("case_sha256") != session.case_sha256 or
                    (record.get("helper_pid"), record.get("helper_start")) != (scope["pid"], scope["start"]) or
                    source.get("phase") != "running" or source.get("nonce") != record.get("source_nonce") or
                    (source.get("helper_pid"), source.get("helper_start")) != (scope["pid"], scope["start"])):
                raise ContractError("EXPERIMENTAL_REJECTED", "The experiment differs from the current authenticated source lifetime")
            allowed = {"startup": {"prepared"}, "view": {"running", "return_requested"},
                       "return-start": {"running", "return_requested"}, "return": {"return_requested"}}
            if record.get("phase") not in allowed[phase]:
                raise ContractError("EXPERIMENTAL_REPLAY", "The source phase is stale or already released")
            peer_start = process_start(peer_pid)
            if peer_start is None or (phase != "startup" and
                    (record.get("source_pid"), record.get("source_start")) != (peer_pid, peer_start)):
                raise ContractError("EXPERIMENTAL_REJECTED", "Another source process cannot consume the admitted case")
            if phase == "return" and "return_started_monotonic" not in record:
                raise ContractError("EXPERIMENTAL_REJECTED", "The source must begin its bounded cleanup before reporting release")
            requested = time.monotonic()
            result = session.relay_check(phase, scope["pid"], scope["start"], peer_pid)
            permitted = {"startup": {"running"}, "view": {"running", "return_requested"},
                         "return-start": {"return_requested"}, "return": {"released"}}
            if (type(result) is not dict or result.get("phase") not in permitted[phase] or
                    result.get("candidate_sha256") != session.candidate_sha256 or
                    result.get("case_sha256") != session.case_sha256):
                raise ContractError("EXPERIMENTAL_REJECTED", "The reviewed observer did not confirm this exact case phase")
            status = {name: result[name] for name in ("phase", "candidate_sha256", "case_sha256")}
            if phase == "return-start" and "return_started_monotonic" not in record:
                # Commit the first cleanup request before acknowledging it.
                # Repeated requests cannot extend either reviewed deadline.
                record = {**record, "return_started_monotonic": requested,
                          "return_deadline": min(record["return_deadline"], requested + session.return_seconds)}
            self.lease.write(session.record_name, {**record, **status,
                "source_pid": peer_pid, "source_start": peer_start})
        return status

    def _handle(self, connection):
        if process_start(self.lease.principal[0]) != self.lease.principal[1]:
            raise ContractError("RESIDENT_UNVERIFIED", "The delegating principal lifetime has ended")
        pid, uid, _ = _peer(connection)
        if uid != os.geteuid():
            raise ContractError("RESIDENT_UNVERIFIED", "The resident peer has another user identity")
        value = _receive(connection)
        signature = value.pop("mac", None)
        kind = value.get("kind")
        if isinstance(kind, str) and kind in {"enroll", "drain"}:
            if set(value) != {"kind", "nonce"} or not isinstance(value["nonce"], str) or len(value["nonce"]) != 64:
                raise ContractError("INVALID_RESIDENT_REQUEST", "The principal lifetime request has an invalid shape")
            if (not isinstance(signature, str) or not hmac.compare_digest(signature, _mac(self.lease.key, value)) or
                    not _lineage(pid, self.lease.principal[0], self.lease.principal[1])):
                raise ContractError("RESIDENT_UNVERIFIED", "Source enrollment did not authenticate the existing principal")
            # Enrollment belongs to principal's immediate trusted helper only.
            with open("/proc/%d/stat" % pid, "rb") as source:
                parent = int(source.read(32769).rpartition(b")")[2].split()[1])
            if parent != self.lease.principal[0]:
                raise ContractError("RESIDENT_UNVERIFIED", "Only the principal's direct source helper may enroll")
            if value["kind"] == "drain":
                self.closing = True
                _send(connection, {"draining": True, "resident_services_stopped": False})
                return
            if self.closing:
                raise ContractError("RESIDENT_UNVERIFIED", "The resident authority is draining its existing descendants")
            scope = {"pid": pid, "start": process_start(pid), "key": secrets.token_hex(32), "sequence": 0}
            if pid in self.scopes:
                raise ContractError("RESIDENT_UNVERIFIED", "This source helper has already enrolled")
            self.scopes[pid] = scope
            _send(connection, {"scope": scope, "server_pid": os.getpid(), "server_start": process_start(os.getpid())})
            return
        if (set(value) != {"helper_pid", "sequence", "operation", "arguments", "stdin"} or
                type(value.get("helper_pid")) is not int or not isinstance(value.get("operation"), str)):
            raise ContractError("INVALID_RESIDENT_REQUEST", "The source service request has an invalid shape")
        scope = self.scopes.get(value.get("helper_pid"))
        if (self.closing or scope is None or not isinstance(signature, str) or
                not hmac.compare_digest(signature, _mac(bytes.fromhex(scope["key"]), value)) or
                not _lineage(pid, scope["pid"], scope["start"]) or
                type(value.get("sequence")) is not int or value["sequence"] != scope["sequence"] + 1):
            raise ContractError("RESIDENT_UNVERIFIED", "The source capability is stale, replayed or outside its live lineage")
        scope["sequence"] = value["sequence"]  # consume even if execution/client fails
        data = value.get("stdin")
        if (data is not None and (not isinstance(data, str) or len(data.encode("utf-8")) > 1024 or
                "\0" in data or value.get("operation") != "wifi" or value.get("arguments") != ["connect"])):
            raise ContractError("INVALID_RESIDENT_REQUEST", "Only bounded WiFi connection data may be sent on stdin")
        if value.get("operation") == "wifi" and value.get("arguments") == ["connect"]:
            fields = data.splitlines() if data is not None else []
            if (len(fields) != 2 or not 1 <= len(fields[0].encode("utf-8")) <= 32 or
                    len(fields[1].encode("utf-8")) > 64):
                raise ContractError("INVALID_RESIDENT_REQUEST", "WiFi connection data must contain a bounded SSID and password")
        self.config.assert_safe()
        experimental = getattr(self.config, "experimental_session", None)
        if value.get("operation") == "experimental-check":
            status = self._experimental(value, scope, pid)
            _send(connection, {"sequence": scope["sequence"], "returncode": 0,
                               "experimental": status, "resident_services_stopped": False})
            return
        if experimental is not None:
            raise ContractError("EXPERIMENTAL_ACTION_DENIED", "View-only source cases cannot mutate shared services")
        argv = operation_argv(self.config, value.get("operation"), value.get("arguments"))
        environment = dict(os.environ)
        for key in (CAPABILITY_ENV, SERVER_ENV, "TRIMUI_PROJECT_STATE_REQUEST", "TRIMUI_PROJECT_RESUME_STATE"):
            environment.pop(key, None)
        result = subprocess.run(argv, input=data.encode("utf-8") if data is not None else None,
            stdin=None if data is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment, timeout=120)
        _send(connection, {"sequence": scope["sequence"], "returncode": result.returncode,
                           "resident_services_stopped": False})

    def serve(self):
        from .principal import _subreaper
        self.config.assert_safe()
        self.lease.assert_clean()
        try:
            os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            pass
        else:
            raise ContractError("FOREIGN_CHILD", "The fresh resident helper already owns another child")
        _subreaper(True)
        path = self.lease.directory / "resident.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))  # never replace an existing authority
            os.chmod(path, 0o600)
            listener.listen(8)
            listener.settimeout(0.1)
            self.lease.write("resident.json", {"server_pid": os.getpid(), "server_start": process_start(os.getpid())})
            while True:
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    connection = None
                if connection is not None:
                    with connection:
                        connection.settimeout(3)
                        try:
                            self._handle(connection)
                        except (OSError, ValueError, ContractError, subprocess.SubprocessError):
                            try:
                                _send(connection, {"blocked": True})
                            except OSError:
                                pass
                no_children = False
                while True:
                    try:
                        child, _ = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        no_children = True
                        break
                    if child == 0:
                        break
                    self.reaped += 1
                self.scopes = {pid: value for pid, value in self.scopes.items() if process_start(pid) == value["start"]}
                if (self.closing or process_start(self.lease.principal[0]) != self.lease.principal[1]) and no_children:
                    break
            path.unlink()


def _connect(lease, server_pid):
    record = lease.read("resident.json")
    if record.get("server_pid") != server_pid or process_start(server_pid) != record.get("server_start"):
        raise ContractError("RESIDENT_UNVERIFIED", "The principal's resident authority is unavailable")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(125)
    try:
        connection.connect(str(lease.directory / "resident.sock"))
        pid, uid, _ = _peer(connection)
        if pid != server_pid or uid != os.geteuid():
            raise ContractError("RESIDENT_UNVERIFIED", "The resident socket belongs to another process")
        return connection
    except BaseException:
        connection.close()
        raise


def source_environment(config):
    """Enroll only the fresh source helper; game helpers never call this."""
    server_pid = int(os.environ[SERVER_ENV])
    lease = PrincipalLease(config)
    with _connect(lease, server_pid) as connection:
        value = {"kind": "enroll", "nonce": secrets.token_hex(32)}
        _send(connection, {**value, "mac": _mac(lease.key, value)})
        result = _receive(connection)
    if "scope" not in result:
        raise ContractError("RESIDENT_UNVERIFIED", "Principal could not enroll its source helper")
    return {CAPABILITY_ENV: json.dumps({"principal": lease.principal, "server_pid": server_pid, "scope": result["scope"]})}


_client_sequence = 0
_client_lock = __import__("threading").Lock()


def _exchange(config, operation, arguments=(), *, stdin_text=None):
    """Use the existing source capability; callers validate their fixed config."""
    capability = json.loads(os.environ[CAPABILITY_ENV])
    lease = PrincipalLease(config, tuple(capability["principal"]))
    scope = capability["scope"]
    if not _lineage(os.getpid(), scope["pid"], scope["start"]):
        raise ContractError("RESIDENT_UNVERIFIED", "The delegation capability is outside its source helper lifetime")
    global _client_sequence
    with _client_lock:
        _client_sequence += 1
        value = {"helper_pid": scope["pid"], "sequence": _client_sequence, "operation": operation,
                 "arguments": list(arguments), "stdin": stdin_text}
        with _connect(lease, capability["server_pid"]) as connection:
            _send(connection, {**value, "mac": _mac(bytes.fromhex(scope["key"]), value)})
            result = _receive(connection)
        if result.get("sequence") != _client_sequence or result.get("returncode") != 0:
            raise ContractError("RESIDENT_OPERATION_FAILED", "The existing shared authority did not accept the delegated operation")
    return result


def experimental_check(config, phase):
    """Check one phase against the resident, never deserialize an admission.

    The fixed source verifier has already bound reviewed inputs and local live
    identities. Its validation is relay-free to avoid recursively calling this
    transport from ProcessSourceConfiguration.assert_safe().
    """
    from .experimental_runtime import ExperimentalRuntimeSession
    from .process_source import ProcessSourceConfiguration
    if (type(config) is not ProcessSourceConfiguration or
            type(getattr(config, "experimental_session", None)) is not ExperimentalRuntimeSession or
            phase not in {"startup", "view", "return-start", "return"}):
        raise ContractError("EXPERIMENTAL_REJECTED", "An exact typed source admission and phase are required")
    config.experimental_session.assert_configuration(config, source_side=True)
    result = _exchange(config, "experimental-check", [phase])
    status = result.get("experimental")
    if (type(status) is not dict or set(status) != {"phase", "candidate_sha256", "case_sha256"} or
            status.get("candidate_sha256") != config.experimental_session.candidate_sha256 or
            status.get("case_sha256") != config.experimental_session.case_sha256 or
            status.get("phase") not in {"running", "return_requested", "released"}):
        raise ContractError("EXPERIMENTAL_REJECTED", "The authenticated response does not match the source case")
    return status


def delegate(operation, arguments=(), *, stdin_text=None):
    """Return False only when no qualified source context exists.

    Once enabled, transport/validation failures raise: the source must never
    fall back to spawning the same persistent service under its foreground.
    """
    from .process_source import configured_runtime
    config = configured_runtime()
    if config is None:
        return False
    config.assert_safe()
    if getattr(config, "experimental_session", None) is not None:
        raise ContractError("EXPERIMENTAL_ACTION_DENIED", "View-only source cases cannot mutate shared services")
    _exchange(config, operation, arguments, stdin_text=stdin_text)
    return True


def delegate_known_command(command):
    if not isinstance(command, (list, tuple)):
        return False
    if len(command) == 3 and command[0] == NETWORK_TOGGLE and command[1] in SERVICES and command[2] in {"True", "False"}:
        return delegate("network-service", command[1:])
    if command and command[0] == NETWORK_TOGGLE:
        from .process_source import configured_runtime
        if configured_runtime() is not None:
            raise ContractError("INVALID_RESIDENT_REQUEST", "The shared-service toggle arguments differ from the fixed reviewed source operation")
    return False


def delegate_radio(radio, configured_command, arguments, *, stdin_text=None):
    from .process_source import configured_runtime
    config = configured_runtime()
    if config is None:
        return False
    config.assert_safe()
    expected = SCRIPT_PREFIX + "bin/spruce_" + radio
    if radio not in {"bluetooth", "wifi"} or configured_command != expected:
        raise ContractError("RESIDENT_UNVERIFIED", "The initialized source radio command differs from its fixed qualified authority")
    if radio == "bluetooth" and tuple(arguments) == ("apply",):
        return delegate("bluetooth-apply")
    if radio == "wifi" and len(arguments) == 1 and arguments[0] in {"apply", "restart", "suspend", "connect", "forget-all"}:
        return delegate("wifi", arguments, stdin_text=stdin_text)
    if arguments and ((radio == "bluetooth" and arguments[0] in {"apply", "boot"}) or
            (radio == "wifi" and arguments[0] in {"apply", "restart", "suspend", "connect", "forget-all"})):
        raise ContractError("INVALID_RESIDENT_REQUEST", "The source radio mutation has unreviewed arguments")
    return False


def run_source_shell(command):
    if isinstance(command, str) and command in TASKS and delegate("task", [Path(command).name]):
        return subprocess.CompletedProcess(command, 0)
    # Unknown commands keep the original source subtree ownership. Their
    # descendants cannot gain a resident bypass by supplying shell syntax.
    return subprocess.run(command, shell=True)


def wait_ready(config, server_pid):
    lease = PrincipalLease(config)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with _connect(lease, server_pid):
                return
        except (OSError, FileNotFoundError):
            if process_start(server_pid) is None:
                break
            time.sleep(0.025)
    raise ContractError("RESIDENT_UNVERIFIED", "The principal resident authority did not become ready")


def request_drain(config, server_pid):
    """Stop accepting new work; exit only after all shared children end.

    A principal-owned maintenance helper may request this. It does not stop,
    detach or certify any service. A live resident descendant keeps it alive.
    """
    lease = PrincipalLease(config)
    with _connect(lease, server_pid) as connection:
        value = {"kind": "drain", "nonce": secrets.token_hex(32)}
        _send(connection, {**value, "mac": _mac(lease.key, value)})
        result = _receive(connection)
    if result != {"draining": True, "resident_services_stopped": False}:
        raise ContractError("RESIDENT_UNVERIFIED", "The resident authority did not accept a principal drain request")
