"""Original ownership of the three tasks started by pinned PyUI mainui.

The optional, source-gated caller in source_integration.py passes the existing
device and manager callback. This module starts those callbacks once, retains
their outcomes and stops only the cooperative audio-route watcher it owns.
It neither discovers nor takes ownership of other PyUI/device workers.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Any, Callable

from psp_shell.runtime import ContractError


class _Task:
    def __init__(self, name: str, callback: Callable[[], None], *, daemon: bool):
        self.finished = threading.Event()
        self.failed = False
        self.thread = threading.Thread(target=self._run, args=(callback,), name=name, daemon=daemon)

    def _run(self, callback):
        try:
            callback()
        except BaseException:
            # Preserve the failure, including SystemExit, instead of treating
            # thread disappearance as successful startup. Keep payloads out of
            # the diagnostics; the existing callback owns detailed logging.
            self.failed = True
        finally:
            self.finished.set()


class RetainedPyUITasks:
    """Retain actual source callbacks and require an independent owner check.

    ``other_owners_idle`` must account for nested startup/audio refresh,
    SmartPro initialization/input/config workers, cache/network/timezone/audio
    workers and staged/active foreground operations. Completion of our two
    one-shot wrappers cannot prove any of those finished. The shipped source
    cannot supply that complete authority yet; never substitute a constant on
    a device. See source_integration.audit_source_lifecycle for the exact pins.
    """

    def __init__(self, device: Any, manager_startup: Callable[[], None], *,
                 other_owners_idle: Callable[[], bool], join_timeout: float = 1.0):
        if (not callable(getattr(device, "perform_startup_tasks", None)) or
                not callable(getattr(device, "watch_audio_route", None)) or
                not callable(manager_startup) or not callable(other_owners_idle)):
            raise ContractError("INVALID_LIFECYCLE", "Existing source callbacks and an independent owner check are required")
        if isinstance(join_timeout, bool) or not isinstance(join_timeout, (int, float)) or not math.isfinite(join_timeout) or not 0 <= join_timeout <= 5:
            raise ContractError("INVALID_LIFECYCLE", "The cooperative stop wait must be bounded to five seconds")
        self.device, self.other_owners_idle = device, other_owners_idle
        self.join_timeout = join_timeout
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._phase = "new"
        self._startup = _Task("PyUI-device-startup", device.perform_startup_tasks, daemon=False)
        self._managers = _Task("PyUI-manager-startup", manager_startup, daemon=False)
        self._stop_audio = threading.Event()
        self._audio = self._new_audio(self._stop_audio)

    def _new_audio(self, stop_event):
        return _Task("PyUI-AudioRoute", lambda: self.device.watch_audio_route(stop_event=stop_event), daemon=True)

    def start(self) -> "RetainedPyUITasks":
        with self._lock:
            if self._phase != "new":
                raise ContractError("LIFECYCLE_ALREADY_STARTED", "The existing startup callbacks may run only once")
            self._phase = "starting"
            try:
                for task in (self._startup, self._managers, self._audio):
                    task.thread.start()
            except BaseException:
                # Even a partially started set stays retained. Do not start a
                # replacement watcher or silently rerun a manager constructor.
                self._stop_audio.set()
                self._phase = "failed"
                raise
            self._phase = "running"
        return self

    def _startup_complete(self):
        return all(task.finished.is_set() and not task.failed and not task.thread.is_alive()
                   for task in (self._startup, self._managers))

    def _audio_running(self):
        return self._audio.thread.is_alive() and not self._audio.finished.is_set() and not self._audio.failed

    def quiescent(self) -> bool:
        with self._lock:
            if self._phase != "running" or not self._startup_complete() or not self._audio_running():
                return False
            if self.other_owners_idle() is not True:
                return False
            # The observer is trusted but may synchronously stop this owner.
            return self._phase == "running" and self._startup_complete() and self._audio_running()

    def stop_background_tasks(self) -> None:
        with self._operation_lock:
            self._stop_background_tasks()

    def _stop_background_tasks(self) -> None:
        with self._lock:
            if self._phase == "stopped":
                return
            if self._phase not in ("running", "stopping") or not self._startup_complete() or self._audio.failed:
                raise ContractError("BACKGROUND_BUSY", "Existing startup has not completed successfully")
            if self.other_owners_idle() is not True:
                raise ContractError("BACKGROUND_BUSY", "Other source owners have not established quiescence")
            self._phase = "stopping"
            self._stop_audio.set()
            task = self._audio
        task.thread.join(self.join_timeout)
        with self._lock:
            if task.thread.is_alive():
                raise ContractError("BACKGROUND_STOP_UNCERTAIN", "The retained audio watcher has not stopped; keep its ownership")
            if task.failed:
                self._phase = "failed"
                raise ContractError("BACKGROUND_FAILED", "The retained audio watcher failed")
            self._phase = "stopped"

    def restore_background_tasks(self) -> None:
        with self._operation_lock:
            self._restore_background_tasks()

    def _restore_background_tasks(self) -> None:
        with self._lock:
            if self._phase == "running":
                # A rejected stop before changing ownership needs no restart.
                if self._audio.failed:
                    raise ContractError("BACKGROUND_FAILED", "The retained audio watcher failed")
                if not self._audio_running():
                    raise ContractError("BACKGROUND_RESTORE_UNCERTAIN", "The running session lost its retained audio watcher")
                return
            if self._phase not in ("stopping", "stopped") or not self._startup_complete() or self._audio.failed:
                raise ContractError("BACKGROUND_RESTORE_UNCERTAIN", "Startup or background ownership cannot be restored safely")
            if self._audio.thread.is_alive():
                # In particular, do not clear its event and do not create a
                # second watcher after a timed-out or partially failed stop.
                raise ContractError("BACKGROUND_RESTORE_UNCERTAIN", "A surviving audio watcher blocks replacement")
            if self.other_owners_idle() is not True:
                raise ContractError("BACKGROUND_RESTORE_UNCERTAIN", "Other source owners are not idle")
            self._stop_audio = threading.Event()
            self._audio = self._new_audio(self._stop_audio)
            try:
                self._audio.thread.start()
            except BaseException:
                self._phase = "failed"
                raise
            self._phase = "running"

    def snapshot(self) -> dict:
        """Bounded diagnostics; no callback payloads or device/user data."""
        with self._lock:
            return {"phase": self._phase, "tasks": [
                {"name": task.thread.name, "started": task.thread.ident is not None,
                 "alive": task.thread.is_alive(), "finished": task.finished.is_set(), "failed": task.failed}
                for task in (self._startup, self._managers, self._audio)]}


@dataclass(frozen=True)
class _SourceCaller:
    binding_factory: Callable
    other_owners_idle: Callable[[], bool]


_caller: _SourceCaller | None = None
_source_tasks: RetainedPyUITasks | None = None


def configure_source_caller(binding_factory: Callable | None, *,
                            other_owners_idle: Callable[[], bool] | None = None,
                            source_use_verified: bool = False) -> None:
    """Trusted source setup only; no file supplies executable callbacks.

    There is no shipped caller registration. A qualified integration registers
    before mainui.start_background_threads. Default unbound behavior runs the
    untouched classic source branch. Clearing is allowed after our tasks stop.
    """
    global _caller, _source_tasks
    if _source_tasks is not None:
        snapshot = _source_tasks.snapshot()
        if snapshot["phase"] not in ("stopped", "failed") or any(item["alive"] for item in snapshot["tasks"]):
            raise ContractError("LIFECYCLE_BUSY", "Retained source tasks must stop before caller replacement")
    if binding_factory is None:
        _caller, _source_tasks = None, None
        return
    if source_use_verified is not True:
        raise ContractError("SOURCE_USE_UNVERIFIED", "Resolve source-use obligations before registering a PyUI source caller")
    if not callable(binding_factory) or not callable(other_owners_idle):
        raise ContractError("INVALID_LIFECYCLE", "A trusted binding factory and independent owner check are required")
    _caller, _source_tasks = _SourceCaller(binding_factory, other_owners_idle), None


def begin_source_tasks(device: Any, manager_startup: Callable[[], None]) -> RetainedPyUITasks | None:
    """Called at the actual source's startup seam, never during inspection."""
    global _source_tasks
    if _caller is None:
        return None
    if _source_tasks is not None:
        raise ContractError("LIFECYCLE_ALREADY_STARTED", "The source session already retained its tasks")
    _source_tasks = RetainedPyUITasks(device, manager_startup, other_owners_idle=_caller.other_owners_idle)
    return _source_tasks.start()


def bind_source_session(main_menu: Any, tasks: RetainedPyUITasks | None):
    """Source main calls after its existing MainMenu and startup are created.

    The factory wraps the existing initialized model references; it must not
    initialize new managers. Readiness remains lazy in InitializedPyUIBinding.
    This function never collects a return receipt or clears foreground state.
    """
    if tasks is None:
        return None
    if _caller is None or tasks is not _source_tasks:
        raise ContractError("INVALID_LIFECYCLE", "The source caller must bind its own retained tasks")
    from .bootstrap import InitializedPyUIBinding
    binding = _caller.binding_factory(main_menu, tasks)
    if (not isinstance(binding, InitializedPyUIBinding) or binding.device is not tasks.device or
            binding.quiescent != tasks.quiescent or
            binding.options["stop_background_tasks"] != tasks.stop_background_tasks or
            binding.options["restore_background_tasks"] != tasks.restore_background_tasks):
        raise ContractError("INVALID_LIFECYCLE", "The binding must retain the source session's lifecycle authority")
    return binding.bind()
