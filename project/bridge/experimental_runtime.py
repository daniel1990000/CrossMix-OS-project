# SPDX-License-Identifier: MIT
"""Explicit private view-only route over the existing PyUI/principal owners.

Fixed reviewed code supplies expectations and in-memory reviews. No metadata,
environment variable or serialized report selects a configuration here. The
shipped selector remains unavailable. Host fixtures use a distinct factory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import sys
import threading
import time

from .experimental import BOOT, DIGEST, ExpectedFile, HostCandidate
from .experimental_journal import HostEvidenceJournal, encoded
from psp_shell.runtime import ContractError, POWER_OFF_ROUTE, SPRUCE_COMMIT


_SEAL = object()
_GATES = ("source_use_verified", "runtime_verified", "hardware_qualified", "process_exit_qualified")
READ_METHODS = frozenset({"system.capabilities", "system.snapshot", "library.systems", "library.query",
                         "library.recent", "library.favorites", "library.random", "tools.list",
                         "settings.get", "controls.capabilities", "appearance.ppsspp.status",
                         "experience.ppsspp.status", "hardware.status", "interface.switch"})


def _reject(code="EXPERIMENTAL_UNAVAILABLE"):
    return ContractError(code, "The reviewed private view-only case is unavailable or blocked; production qualification is unchanged")


def _digest(value):
    return type(value) is str and DIGEST.fullmatch(value)


@dataclass(frozen=True)
class SourceUseEvidenceReview:
    """A trusted review of retained delivery or owner-attested permission/scope.

    Construct only after inspecting real retained evidence. This type cannot
    authenticate correspondence and has no dictionary/report deserializer.
    """
    retained_evidence_sha256: str
    scope_review_sha256: str
    source_commit: str = SPRUCE_COMMIT
    scope: str = "private-source-candidate"
    actual_delivery_reviewed: bool = False
    owner_permission_reviewed: bool = False


@dataclass(frozen=True)
class RecoveryRuntimeReview:
    backup_manifest_sha256: str
    retained_readback_sha256: str
    restore_rehearsal_sha256: str
    observed_runtime_sha256: str
    independent_media_reviewed: bool = False
    physical_restore_reviewed: bool = False
    original_device_observed: bool = False


@dataclass(frozen=True)
class HostFixtureReview:
    reference_sha256: str
    provenance: str = "synthetic-host-fixture"


@dataclass(frozen=True)
class RuntimeCandidate:
    """Independent reviewed build and complete installed import/runtime identities.

    `files` uses SD-relative names plus `rootfs/...` for installed system inputs.
    `imports` includes independently reviewed runtime imports/dependencies beyond
    the mandatory source/project set. Observations must not create expectations.
    """
    build: HostCandidate
    files: tuple[ExpectedFile, ...]
    imports: tuple[str, ...]
    sd_root: str
    module_root: str
    state_dir: str
    boot_id: str
    principal_pid: int
    principal_start: str
    media_sha256: str
    firmware_version: str
    filesystem: str
    case_sha256: str

    def __post_init__(self):
        if (type(self.build) is not HostCandidate or type(self.files) is not tuple or
                not 0 < len(self.files) <= 4096 or any(type(item) is not ExpectedFile for item in self.files) or
                len({item.path for item in self.files}) != len(self.files) or
                type(self.imports) is not tuple or not self.imports or len(set(self.imports)) != len(self.imports) or
                any(type(value) is not str for value in self.imports) or
                type(self.boot_id) is not str or not BOOT.fullmatch(self.boot_id) or
                type(self.principal_pid) is not int or self.principal_pid <= 0 or
                type(self.principal_start) is not str or not self.principal_start.isascii() or not self.principal_start.isdigit() or
                not _digest(self.media_sha256) or not _digest(self.case_sha256) or
                any(type(value) is not str or not 1 <= len(value) <= 64 or any(ord(c) < 32 for c in value)
                    for value in (self.firmware_version, self.filesystem))):
            raise _reject()
        roots = [Path(value).absolute() for value in (self.sd_root, self.module_root, self.state_dir)]
        if (any(not Path(value).is_absolute() or ".." in Path(value).parts for value in
                (self.sd_root, self.module_root, self.state_dir)) or not roots[1].is_relative_to(roots[0]) or
                roots[1] == roots[0] or roots[2] == roots[1] or roots[2].is_relative_to(roots[1])):
            raise _reject()
        expected = {item.path: item.sha256 for item in self.files}
        from .principal_integration import SOURCE_BLOBS, REQUIRED_PROJECT_MODULES
        relative_modules = roots[1].relative_to(roots[0]).as_posix()
        mandatory = set(SOURCE_BLOBS) | {relative_modules + "/" + path.removeprefix("app/")
                                        for path in REQUIRED_PROJECT_MODULES}
        if (not mandatory.issubset(expected) or not set(self.imports).issubset(expected) or
                not any(path.startswith("rootfs/") for path in self.imports)):
            raise _reject("EXPERIMENTAL_INCOMPLETE_IDENTITY")
        for item in self.build.files:
            if item.path.startswith("app/") and expected.get(relative_modules + "/" + item.path[4:]) != item.sha256:
                raise _reject("EXPERIMENTAL_INCOMPLETE_IDENTITY")
        object.__setattr__(self, "files", tuple(sorted(self.files, key=lambda item: item.path)))

    @property
    def sha256(self):
        return hashlib.sha256(encoded(asdict(self))).hexdigest()


@dataclass(frozen=True)
class RuntimeObservation:
    boot_id: str
    principal_pid: int
    principal_start: str
    media_sha256: str
    files: tuple[ExpectedFile, ...]
    firmware_version: str
    filesystem: str
    model: str = "TG5040"
    platform: str = "SmartPro"
    architecture: str = "aarch64"
    live_device: bool = False
    owners_ready: bool = True
    dirty: bool = False
    staged_command: bool = False


class ReadOnlyViewSettings:
    """In-memory view preferences; no SettingsStore lock/recovery/write path."""
    def __init__(self, preferences):
        from psp_shell.settings import DEFAULT_PREFERENCES
        self._preferences = copy.deepcopy(DEFAULT_PREFERENCES)
        for key in self._preferences:
            if key in preferences:
                self._preferences[key] = copy.deepcopy(preferences[key])

    def get(self):
        return {"schema": 1, "generation": 0, "preferences": copy.deepcopy(self._preferences)}


class ExperimentalRuntimeSession:
    """Typed one-case authority; existing authenticated relay owns source status."""
    def __init__(self, seal, expected, observe, journal, *, fixture, clock, issued,
                 view_seconds, return_seconds, prerequisite_sha256):
        if seal is not _SEAL:
            raise _reject()
        self.expected, self._observe, self.journal = expected, observe, journal
        self.fixture, self._clock, self._last = fixture, clock, issued
        self._prerequisite_sha256 = prerequisite_sha256
        self._issued, self._phase, self._config = issued, "prepared", None
        self._thread = threading.get_ident()
        self._source_owner = self._owners = self._context = None
        self._source_bound = False
        self._return_requested = False
        self._relay = None
        self.view_seconds, self.return_seconds = view_seconds, return_seconds
        self.observation_deadline = issued + 60 + view_seconds + return_seconds

    @property
    def candidate_sha256(self):
        return hashlib.sha256(encoded([self.expected.sha256, self._prerequisite_sha256])).hexdigest()

    @property
    def case_sha256(self):
        return self.expected.case_sha256

    @property
    def record_name(self):
        return "experimental-" + self.case_sha256 + ".json"

    @property
    def phase(self):
        return self._phase

    def __copy__(self):
        raise TypeError("Experimental sessions cannot be copied")

    def __deepcopy__(self, _):
        raise TypeError("Experimental sessions cannot be copied")

    def __reduce_ex__(self, _):
        raise TypeError("Experimental sessions cannot be serialized")

    def _now(self):
        try:
            value = self._clock()
            if (threading.get_ident() != self._thread or type(value) not in {int, float} or
                    not math.isfinite(value) or value < self._last):
                raise _reject()
            self._last = value
            return value
        except BaseException:
            self._phase = "blocked"
            raise _reject("EXPERIMENTAL_CLOCK") from None

    def _event(self, name):
        try:
            self.journal.append(name, int(self._now() * 1e9))
        except BaseException:
            self._phase = "blocked"
            raise

    def block(self, reason="blocked"):
        self.record_blocked(reason)
        raise _reject("EXPERIMENTAL_BLOCKED")

    def record_blocked(self, reason="blocked"):
        self._phase = "blocked"
        self._event(reason if reason in {"expired", "identity_changed", "callback_failed", "action_denied"} else "blocked")

    def _observation(self):
        try:
            value = self._observe()
        except BaseException:
            self.block("identity_changed")
        expected = self.expected
        if (type(value) is not RuntimeObservation or type(value.live_device) is not bool or value.live_device is self.fixture or
                value.boot_id != expected.boot_id or value.principal_pid != expected.principal_pid or
                value.principal_start != expected.principal_start or value.media_sha256 != expected.media_sha256 or
                value.files != expected.files or value.firmware_version != expected.firmware_version or
                value.filesystem != expected.filesystem or value.model != "TG5040" or
                value.platform != "SmartPro" or value.architecture != "aarch64" or
                value.owners_ready is not True or value.dirty is not False or value.staged_command is not False):
            self.block("identity_changed")
        return value

    def assert_configuration(self, config, *, source_side=False):
        self._now()
        if self._phase in {"blocked", "closed"}:
            raise _reject("EXPERIMENTAL_BLOCKED")
        if self._config is not None and self._config is not config:
            raise _reject("EXPERIMENTAL_CONFIG_CHANGED")
        expected = self.expected
        if (getattr(config, "experimental_session", None) is not self or
                str(config.sd_root) != expected.sd_root or str(config.state_dir) != expected.state_dir or
                any(config.profile.get(name) is not False for name in _GATES) or
                config.profile.get("source_commit") != SPRUCE_COMMIT or
                config.profile.get("required_hashes") != {item.path: item.sha256 for item in expected.files} or
                config.execution_environment != ("host-fixture" if self.fixture else "private-experimental") or
                any(getattr(config, name) is not None for name in
                    ("adapters", "completion_observer", "command_environment", "resume_evidence", "mode_actions"))):
            raise _reject()
        from .process_source import process_start
        from psp_shell.health import _boot_id
        if process_start(expected.principal_pid) != expected.principal_start or _boot_id() != expected.boot_id:
            self.block("identity_changed")
        if self.fixture:
            root = Path(config.sd_root).resolve()
            if root == Path("/mnt/SDCARD") or Path("/mnt/SDCARD") in root.parents:
                raise _reject("INVALID_FIXTURE")
        elif (expected.sd_root != "/mnt/SDCARD" or
              expected.module_root != "/mnt/SDCARD/App/PSPMode/integration/app" or
              Path(__file__).resolve().parent.parent != Path(expected.module_root) or
              config.private_runtime != Path("/tmp/trimui-project-principal")):
            raise _reject("EXPERIMENTAL_INSTALLATION_CHANGED")
        observed, preferences = config.inventory(), config.preferences()
        if (not isinstance(observed, dict) or not isinstance(preferences, dict) or
                observed.get("hashes") != config.profile["required_hashes"] or
                observed.get("live") is self.fixture or type(observed.get("live")) is not bool or
                preferences.get("enableButtonWatchers") is not False or preferences.get("poweroffCmd") != POWER_OFF_ROUTE):
            self.block("identity_changed")
        if os.path.lexists(config.staged_command):
            self.block("identity_changed")
        self._observation()
        self._config = config

    def before_source(self, config):
        self.assert_configuration(config)
        if self._phase != "prepared" or self._now() >= self._issued + 60:
            self.block("expired")
        self._phase = "source_running"
        self._event("started")

    def _record(self):
        from .resident import PrincipalLease
        value = PrincipalLease(self._config, (self.expected.principal_pid, self.expected.principal_start)).read(self.record_name)
        if (value.get("candidate_sha256") != self.candidate_sha256 or value.get("case_sha256") != self.case_sha256 or
                value.get("phase") not in {"reserved", "prepared", "running", "return_requested", "released"}):
            raise _reject("EXPERIMENTAL_RELAY_CHANGED")
        return value

    def relay_check(self, phase, helper_pid, helper_start, peer_pid):
        self.assert_configuration(self._config)
        if phase not in {"startup", "view", "return-start", "return"}:
            self.block("action_denied")
        record = self._record()
        from .process_source import process_start
        if (record.get("helper_pid") != helper_pid or record.get("helper_start") != helper_start or
                process_start(helper_pid) != helper_start or process_start(peer_pid) is None):
            self.block("identity_changed")
        owner = (peer_pid, process_start(peer_pid))
        if self._source_owner is None:
            if phase != "startup" or record["phase"] not in {"reserved", "prepared"}:
                self.block("identity_changed")
            self._source_owner = owner
        elif self._source_owner != owner or phase == "startup":
            self.block("identity_changed")
        now = self._now()
        start = record.get("started_monotonic")
        if type(start) not in {int, float} or not math.isfinite(start) or start > now:
            self.block("identity_changed")
        view_deadline = record.get("view_deadline", start + self.view_seconds)
        return_deadline = record.get("return_deadline", view_deadline + self.return_seconds)
        if phase == "startup" and now >= start + 60 or now >= return_deadline:
            self.block("expired")
        current = record["phase"]
        if current == "released":
            self.block("action_denied")
        if phase == "return-start":
            current = "return_requested"
            self._event("return_requested")
        elif phase == "return":
            requested = record.get("return_started_monotonic")
            if (current != "return_requested" or type(requested) not in {int, float} or
                    not math.isfinite(requested) or requested > now or return_deadline > requested + self.return_seconds):
                self.block("action_denied")
            current = "released"
        elif now >= view_deadline:
            current = "return_requested"
        elif current in {"reserved", "prepared"}:
            current = "running"
        self._phase = current
        return {"phase": current, "candidate_sha256": self.candidate_sha256, "case_sha256": self.case_sha256}

    def source_observation_policy(self):
        from .principal import TreeObservationPolicy
        record = self._record()
        start, view_deadline, return_deadline = (record.get(name) for name in
                                                 ("started_monotonic", "view_deadline", "return_deadline"))
        if (any(type(value) not in {int, float} or not math.isfinite(value) or value < 0
                for value in (start, view_deadline, return_deadline)) or
                view_deadline != start + self.view_seconds or return_deadline != view_deadline + self.return_seconds):
            self.block("identity_changed")
        self.observation_deadline = return_deadline
        def active():
            current = self._record()
            if current["phase"] == "released":
                return False
            deadline = current.get("return_deadline")
            if (type(deadline) not in {int, float} or not math.isfinite(deadline) or
                    deadline > self.observation_deadline or self._now() >= deadline):
                raise _reject("EXPERIMENTAL_RETURN_EXPIRED")
            return True
        def blocked(_):
            self.record_blocked("expired")
        return TreeObservationPolicy(self.observation_deadline, blocked, observation_active=active)

    def after_source(self, config, kernel_completion):
        self.assert_configuration(config)
        from .principal import OwnedTreeCompletion, _KERNEL_SEAL
        if (type(kernel_completion) is not OwnedTreeCompletion or kernel_completion._seal is not _KERNEL_SEAL or
                kernel_completion.children_reaped < 1 or kernel_completion.exit_status != 0 or self._record()["phase"] != "released"):
            self.block()
        self._phase = "closed"
        self._event("completed")

    def _loaded_imports(self):
        if self.fixture:
            return
        names = set()
        modules = tuple(sys.modules.values())
        if len(modules) > 4096:
            self.block("identity_changed")
        for module in modules:
            filename = getattr(module, "__file__", None)
            if not filename:
                continue
            path = Path(filename)
            if path.suffix == ".pyc":
                try:
                    path = Path(importlib.util.source_from_cache(str(path)))
                except ValueError:
                    self.block("identity_changed")
            path = path.resolve()
            try:
                name = path.relative_to(Path(self.expected.sd_root)).as_posix()
            except ValueError:
                name = "rootfs" + path.as_posix()
            names.add(name)
        executable = Path(sys.executable).resolve()
        names.add("rootfs" + executable.as_posix())
        if not names.issubset({item.path for item in self.expected.files}):
            self.block("identity_changed")

    def attach_context(self, context):
        self.assert_configuration(self._config, source_side=True)
        if (context.experimental_session is not self or str(context.sd_root) != self.expected.sd_root or
                str(context.state_dir) != self.expected.state_dir or
                context.execution_environment != self._config.execution_environment or
                context.quiescent() is not True):
            raise _reject()
        owners = (context.device, context.display, context.controller, context.main_menu)
        if self._owners is None:
            self._owners = owners
        elif any(a is not b for a, b in zip(owners, self._owners)):
            self.block("identity_changed")
        self._context = context
        self._loaded_imports()
        if not self._source_bound:
            self._remote("startup")
            self._source_bound = True
        else:
            self.check_view()

    def _remote(self, phase):
        from .resident import experimental_check
        result = experimental_check(self._config, phase)
        if (type(result) is not dict or result.get("candidate_sha256") != self.candidate_sha256 or
                result.get("case_sha256") != self.case_sha256 or
                result.get("phase") not in {"running", "return_requested", "released"}):
            self.block("identity_changed")
        self._phase = result["phase"]
        return self._phase

    def check_view(self):
        self.assert_configuration(self._config, source_side=True)
        self._check_owners()
        self._loaded_imports()
        if not self._source_bound or self._phase in {"released", "closed", "blocked"}:
            raise _reject()
        return self._remote("view") == "running"

    def _check_owners(self):
        context = self._context
        if context is None or self._owners is None:
            raise _reject()
        owners = (context.device, context.display, context.controller, context.main_menu)
        try:
            if context.assert_owners is not None:
                context.assert_owners()
            safe = context.quiescent() is True and all(a is b for a, b in zip(owners, self._owners))
        except BaseException:
            self.block("identity_changed")
        if not safe:
            self.block("identity_changed")

    def check_method(self, method, params):
        if (method not in READ_METHODS or method == "library.systems" and params.get("refresh") or
                method == "interface.switch" and params.get("interface") != "classic"):
            self.block("action_denied")
        if not self.check_view():
            raise _reject("EXPERIMENTAL_RETURN_REQUESTED")

    def release_source(self, *, owners_restored, idle, staged_command_absent):
        if owners_restored is not True or idle is not True or staged_command_absent is not True:
            self.block()
        self.assert_configuration(self._config, source_side=True)
        self._check_owners()
        if not self._source_bound or not self._return_requested or self._phase in {"blocked", "released", "closed"}:
            raise _reject()
        if self._remote("return") != "released":
            self.block()

    def request_return(self):
        self.assert_configuration(self._config, source_side=True)
        self._check_owners()
        if not self._source_bound or self._phase not in {"running", "return_requested"}:
            raise _reject()
        if self._remote("return-start") != "return_requested":
            self.block()
        self._return_requested = True

    def close(self):
        self.journal.close()


def _prepare(expected, observe, evidence_directory, *, fixture, clock, view_seconds, return_seconds, prerequisite_sha256):
    if type(expected) is not RuntimeCandidate or not callable(observe) or not callable(clock):
        raise _reject()
    root = Path(expected.sd_root)
    if (fixture and (root == Path("/mnt/SDCARD") or Path("/mnt/SDCARD") in root.parents) or
            not fixture and (expected.sd_root != "/mnt/SDCARD" or
                expected.module_root != "/mnt/SDCARD/App/PSPMode/integration/app")):
        raise _reject("EXPERIMENTAL_INSTALLATION_CHANGED")
    if any(type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= maximum
           for value, maximum in ((view_seconds, 120), (return_seconds, 5))):
        raise _reject()
    now = clock()
    if type(now) not in {int, float} or not math.isfinite(now) or now < 0:
        raise _reject()
    candidate_sha256 = hashlib.sha256(encoded([expected.sha256, prerequisite_sha256])).hexdigest()
    journal = HostEvidenceJournal(evidence_directory, session=expected.case_sha256, candidate=candidate_sha256,
                                  boot=hashlib.sha256(expected.boot_id.encode("ascii")).hexdigest(),
                                  owner=hashlib.sha256(encoded([expected.principal_pid, expected.principal_start])).hexdigest(),
                                  provenance="host_fixture" if fixture else "private_experimental")
    result = ExperimentalRuntimeSession(_SEAL, expected, observe, journal, fixture=fixture,
                                         clock=clock, issued=now, view_seconds=view_seconds, return_seconds=return_seconds,
                                         prerequisite_sha256=prerequisite_sha256)
    try:
        result._observation()
        result._event("prepared")
        return result
    except BaseException:
        journal.close()
        raise


def prepare_private_session(expected, observe, evidence_directory, *, source_use, recovery_runtime,
                            clock=time.monotonic, view_seconds=120, return_seconds=5):
    if (type(source_use) is not SourceUseEvidenceReview or source_use.source_commit != SPRUCE_COMMIT or
            source_use.scope != "private-source-candidate" or
            type(source_use.actual_delivery_reviewed) is not bool or type(source_use.owner_permission_reviewed) is not bool or
            not (source_use.actual_delivery_reviewed is True or source_use.owner_permission_reviewed is True) or
            not _digest(source_use.retained_evidence_sha256) or not _digest(source_use.scope_review_sha256) or
            type(recovery_runtime) is not RecoveryRuntimeReview or
            any(getattr(recovery_runtime, name) is not True for name in
                ("independent_media_reviewed", "physical_restore_reviewed", "original_device_observed")) or
            any(not _digest(getattr(recovery_runtime, name)) for name in
                ("backup_manifest_sha256", "retained_readback_sha256", "restore_rehearsal_sha256", "observed_runtime_sha256"))):
        raise _reject("EXPERIMENTAL_PREREQUISITES_MISSING")
    return _prepare(expected, observe, evidence_directory, fixture=False, clock=clock,
                     view_seconds=view_seconds, return_seconds=return_seconds,
                     prerequisite_sha256=hashlib.sha256(encoded([asdict(source_use), asdict(recovery_runtime)])).hexdigest())


def prepare_fixture_session(expected, observe, evidence_directory, *, review,
                            clock=time.monotonic, view_seconds=120, return_seconds=5):
    if type(review) is not HostFixtureReview or review.provenance != "synthetic-host-fixture" or not _digest(review.reference_sha256):
        raise _reject("INVALID_FIXTURE")
    return _prepare(expected, observe, evidence_directory, fixture=True, clock=clock,
                     view_seconds=view_seconds, return_seconds=return_seconds,
                     prerequisite_sha256=hashlib.sha256(encoded(asdict(review))).hexdigest())


def configuration():
    """Unavailable until separately reviewed fixed private configuration exists.

    A private review replaces this exact source function with independently
    reviewed typed inputs; no saved profile, file name or flag selects code.
    The production qualified_runtime selector remains separately unavailable.
    """
    return None
