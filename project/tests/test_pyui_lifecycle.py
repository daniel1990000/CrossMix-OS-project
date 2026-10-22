"""Retained original callbacks and isolated pinned-source lifecycle acceptance.

No test starts an installed PyUI, reads input devices or qualifies a device.
True source-use/profile values below are explicit fixture inputs, not evidence
that notification or source-use obligations were completed.
"""
import ast
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.bootstrap import ExistingPyUIModels, InitializedPyUIBinding
from bridge.lifecycle import (RetainedPyUITasks, begin_source_tasks,
                              bind_source_session, configure_source_caller)
from bridge.pyui_entry import bind_context_factory
from bridge.source_integration import (DEVICE_COMMON, MAINUI, SOURCE_BLOBS,
                                      audit_source_lifecycle, stage_lifecycle_hook)
from psp_shell.runtime import ContractError


SOURCE = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.audio_started = threading.Event()
        self.ready = threading.Event()
        self.ready.set()
        def watch(*, stop_event):
            self.events.append("audio-start")
            self.audio_started.set()
            stop_event.wait(2)
            self.events.append("audio-stop")
        self.device = SimpleNamespace(perform_startup_tasks=lambda: self.events.append("device-startup"),
                                      watch_audio_route=watch, run_game=lambda _: None)
        self.tasks = []
        self.external_idle = True
        self.addCleanup(self.cleanup_tasks)
        self.addCleanup(bind_context_factory, None)

    def cleanup_tasks(self):
        # Only tests may force their own fixture events. The runtime never
        # kills an existing worker to make a foreground handoff look safe.
        for tasks in self.tasks:
            tasks._stop_audio.set()
            for task in (tasks._startup, tasks._managers, tasks._audio):
                if task.thread.ident is not None:
                    task.thread.join(2)
            tasks.other_owners_idle = lambda: True  # Fixture teardown only.
            if tasks._startup_complete() and not tasks._audio.failed:
                tasks.stop_background_tasks()
        configure_source_caller(None)

    def start(self, **overrides):
        kwargs = dict(device=self.device, manager_startup=lambda: self.events.append("manager-startup"),
                      other_owners_idle=lambda: self.external_idle, join_timeout=0.05)
        kwargs.update(overrides)
        tasks = RetainedPyUITasks(**kwargs)
        self.tasks.append(tasks)
        tasks.start()
        tasks._startup.thread.join(1)
        tasks._managers.thread.join(1)
        self.assertTrue(self.audio_started.wait(1))
        return tasks

    def test_startup_runs_once_and_restore_only_restarts_its_joined_audio_watcher(self):
        tasks = self.start()
        self.assertTrue(tasks.quiescent())
        with self.assertRaises(ContractError):
            tasks.start()
        tasks.stop_background_tasks()
        tasks.stop_background_tasks()
        self.assertEqual(tasks.snapshot()["phase"], "stopped")
        self.assertFalse(any(task["alive"] for task in tasks.snapshot()["tasks"]))
        self.assertFalse(tasks.quiescent())
        self.audio_started.clear()
        tasks.restore_background_tasks()
        self.assertTrue(self.audio_started.wait(1))
        tasks.restore_background_tasks()
        self.assertEqual(self.events.count("device-startup"), 1)
        self.assertEqual(self.events.count("manager-startup"), 1)
        self.assertEqual(self.events.count("audio-start"), 2)
        self.assertTrue(tasks.quiescent())

    def test_pending_or_failed_startup_never_proves_quiescence(self):
        unblock = threading.Event()
        self.addCleanup(unblock.set)
        device = SimpleNamespace(perform_startup_tasks=unblock.wait, watch_audio_route=self.device.watch_audio_route)
        tasks = RetainedPyUITasks(device, lambda: None, other_owners_idle=lambda: True)
        self.tasks.append(tasks)
        tasks.start()
        self.assertFalse(tasks.quiescent())
        with self.assertRaises(ContractError) as caught:
            tasks.stop_background_tasks()
        self.assertEqual(caught.exception.code, "BACKGROUND_BUSY")
        tasks.restore_background_tasks()
        unblock.set()
        tasks._startup.thread.join(1)
        tasks._managers.thread.join(1)
        self.assertTrue(tasks.quiescent())
        def failed():
            raise SystemExit(3)
        failed_tasks = self.start(manager_startup=failed)
        self.assertFalse(failed_tasks.quiescent())
        self.assertTrue(failed_tasks.snapshot()["tasks"][1]["failed"])
        with self.assertRaises(ContractError):
            failed_tasks.stop_background_tasks()

    def test_nested_or_unknown_owners_remain_a_separate_positive_requirement(self):
        tasks = self.start()
        for observation in (False, None, 1, "yes"):
            self.external_idle = observation
            self.assertFalse(tasks.quiescent())
            with self.assertRaises(ContractError):
                tasks.stop_background_tasks()
            tasks.restore_background_tasks()
            self.assertEqual(self.events.count("audio-start"), 1)
        self.external_idle = True
        self.assertTrue(tasks.quiescent())

    def test_timed_out_stop_retains_the_surviving_watcher_and_blocks_replacement(self):
        unblock = threading.Event()
        def watch(*, stop_event):
            self.events.append("audio-start")
            self.audio_started.set()
            unblock.wait(2)
        self.device.watch_audio_route = watch
        tasks = self.start()
        with self.assertRaises(ContractError) as caught:
            tasks.stop_background_tasks()
        self.assertEqual(caught.exception.code, "BACKGROUND_STOP_UNCERTAIN")
        self.assertFalse(tasks.quiescent())
        with self.assertRaises(ContractError) as caught:
            tasks.restore_background_tasks()
        self.assertEqual(caught.exception.code, "BACKGROUND_RESTORE_UNCERTAIN")
        self.assertEqual(self.events.count("audio-start"), 1)
        unblock.set()
        tasks._audio.thread.join(1)
        tasks.restore_background_tasks()
        tasks._audio.thread.join(1)
        self.assertEqual(self.events.count("audio-start"), 2)

    def test_failed_or_partially_started_set_never_restarts_managers(self):
        tasks = RetainedPyUITasks(self.device, lambda: self.events.append("manager-startup"),
                                  other_owners_idle=lambda: True)
        self.tasks.append(tasks)
        with patch.object(tasks._managers.thread, "start", side_effect=RuntimeError("fixture start failure")):
            with self.assertRaises(RuntimeError):
                tasks.start()
        tasks._startup.thread.join(1)
        self.assertEqual(tasks.snapshot()["phase"], "failed")
        with self.assertRaises(ContractError):
            tasks.restore_background_tasks()
        self.assertNotIn("manager-startup", self.events)
        self.assertFalse(tasks.quiescent())

    def test_successful_watcher_disappearance_cannot_qualify_a_running_session(self):
        def ended(*, stop_event):
            self.audio_started.set()
        self.device.watch_audio_route = ended
        tasks = self.start()
        tasks._audio.thread.join(1)
        self.assertFalse(tasks.quiescent())
        with self.assertRaises(ContractError) as caught:
            tasks.restore_background_tasks()
        self.assertEqual(caught.exception.code, "BACKGROUND_RESTORE_UNCERTAIN")
        # Source USB-audio-unsupported returns also need an explicit qualified
        # no-watcher contract. A successful return is not that observation.
        self.assertEqual(tasks.snapshot()["phase"], "running")
        self.assertFalse(tasks.snapshot()["tasks"][2]["failed"])

    def test_unbound_source_path_does_not_start_any_task_or_import_optional_ui(self):
        self.assertIsNone(begin_source_tasks(self.device, lambda: self.events.append("manager-startup")))
        self.assertIsNone(bind_source_session(object(), None))
        self.assertEqual(self.events, [])
        with self.assertRaises(ContractError):
            configure_source_caller(lambda *_: None, other_owners_idle=lambda: True)
        for timeout in (True, -1, float("nan"), 6):
            with self.assertRaises(ContractError):
                RetainedPyUITasks(self.device, lambda: None, other_owners_idle=lambda: True, join_timeout=timeout)

    def fixture_binding(self, tasks, state_dir):
        display = SimpleNamespace(renderer=SimpleNamespace(renderer=object()),
                                  window=SimpleNamespace(window=object()), present=lambda: None)
        controller = SimpleNamespace(**{name: lambda *_, **__: None for name in (
            "get_input", "still_held_down", "clear_input_queue", "clear_last_input", "last_input")})
        models = ExistingPyUIModels(SimpleNamespace(get_active_systems=lambda: []), lambda _: [],
            SimpleNamespace(_init_event=self.ready, get_favorites=lambda: []),
            SimpleNamespace(_init_event=self.ready, get_recents=lambda: []))
        return InitializedPyUIBinding(device=self.device, display=display, controller=controller,
            models=models, state_dir=state_dir, profile={}, inventory=lambda: {}, preferences=lambda: {},
            quiescent=tasks.quiescent, stop_background_tasks=tasks.stop_background_tasks,
            restore_background_tasks=tasks.restore_background_tasks,
            release_input=lambda: None, restore_input=lambda: None)

    def test_source_caller_binds_only_the_actual_retained_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            menu = object()
            bindings = []
            def factory(main_menu, tasks):
                self.assertIs(main_menu, menu)
                if not bindings:
                    bindings.append(self.fixture_binding(tasks, temporary))
                return bindings[0]
            configure_source_caller(factory, other_owners_idle=lambda: self.external_idle, source_use_verified=True)
            tasks = begin_source_tasks(self.device, lambda: self.events.append("manager-startup"))
            self.tasks.append(tasks)
            tasks._startup.thread.join(1)
            tasks._managers.thread.join(1)
            binding = bind_source_session(menu, tasks)
            self.assertIs(binding.device, self.device)
            self.assertEqual(binding.options["stop_background_tasks"], tasks.stop_background_tasks)
            self.assertFalse(binding._profile.get("hardware_qualified", False))
            self.assertIsNone(binding.verify_return)
            with self.assertRaises(ContractError):
                begin_source_tasks(self.device, lambda: None)
            with self.assertRaises(ContractError):
                configure_source_caller(None)
            binding.quiescent = lambda: True
            with self.assertRaises(ContractError):
                bind_source_session(menu, tasks)


class SourceLifecycleAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / MAINUI).is_file():
            raise unittest.SkipTest("Untouched pinned spruce source not available; set SPRUCE_SOURCE_ROOT")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.patched = cls.root / "patched"
        cls.audit = audit_source_lifecycle(SOURCE)
        # Explicit source-use fixture gate only. Do not persist the derivative
        # or treat this test input as a completed notification obligation.
        cls.record = stage_lifecycle_hook(SOURCE, cls.root / "stage", source_use_verified=True)
        for path in (MAINUI, DEVICE_COMMON):
            target = cls.patched / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        subprocess.run(["git", "apply", "--check", str(cls.root / "stage/0002-pyui-retained-startup.patch")],
                       cwd=cls.patched, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(cls.root / "stage/0002-pyui-retained-startup.patch")],
                       cwd=cls.patched, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_exact_source_audit_preserves_unaccounted_owners_and_return_gate(self):
        self.assertEqual(len(self.audit["sources"]), len(SOURCE_BLOBS))
        self.assertEqual(len(self.audit["unaccounted_owners"]), 7)
        self.assertFalse(self.audit["principal_return_authority_qualified"])
        self.assertFalse(self.audit["source_caller_installed"])
        self.assertFalse(self.record["hardware_execution_enabled"])
        for item in self.record["transformed"]:
            self.assertEqual(hashlib.sha256((self.patched / item["path"]).read_bytes()).hexdigest(), item["patched_sha256"])

    def test_staging_refuses_unresolved_source_use_or_source_tree_outputs(self):
        with self.assertRaises(ContractError) as caught:
            stage_lifecycle_hook(SOURCE, self.root / "not-produced")
        self.assertEqual(caught.exception.code, "SOURCE_USE_UNVERIFIED")
        self.assertFalse((self.root / "not-produced").exists())
        with self.assertRaises(ContractError) as caught:
            stage_lifecycle_hook(SOURCE, SOURCE / "never-produce", source_use_verified=True)
        self.assertEqual(caught.exception.code, "UNSAFE_STAGING")

    def test_changed_or_symlink_source_is_rejected_before_a_patch_is_produced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            for path in SOURCE_BLOBS:
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / path, target)
            (source / MAINUI).write_bytes((source / MAINUI).read_bytes() + b"\n# changed\n")
            with self.assertRaises(ContractError) as caught:
                stage_lifecycle_hook(source, root / "stage", source_use_verified=True)
            self.assertEqual(caught.exception.code, "SOURCE_MISMATCH")
            self.assertFalse((root / "stage").exists())
            (source / MAINUI).unlink()
            (source / MAINUI).symlink_to(SOURCE / MAINUI)
            with self.assertRaises(ContractError):
                audit_source_lifecycle(source)

    def test_actual_source_startup_function_reaches_retained_branch_only_when_registered(self):
        module = ast.parse((self.patched / MAINUI).read_text())
        function = next(item for item in module.body if isinstance(item, ast.FunctionDef) and item.name == "start_background_threads")
        events = []
        device = SimpleNamespace(perform_startup_tasks=lambda: events.append("device"),
                                 watch_audio_route=lambda **_: events.append("audio"))
        namespace = {"threading": threading, "Device": SimpleNamespace(get_device=lambda: device),
                     "background_startup": lambda: events.append("managers")}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<actual pinned start_background_threads>", "exec"), namespace)
        # No trusted registration: the existing source branch is preserved.
        self.assertIsNone(namespace["start_background_threads"]())
        for thread in list(threading.enumerate()):
            if thread.name == "AudioRoute":
                thread.join(1)
        self.assertCountEqual(events, ["device", "managers", "audio"])
        configure_source_caller(lambda *_: None, other_owners_idle=lambda: False, source_use_verified=True)
        try:
            tasks = namespace["start_background_threads"]()
            self.assertIsInstance(tasks, RetainedPyUITasks)
            for task in (tasks._startup, tasks._managers, tasks._audio):
                task.thread.join(1)
            self.assertFalse(tasks.quiescent(), "Source wrappers cannot qualify unknown descendants")
            tasks.other_owners_idle = lambda: True  # Local fixture cleanup only.
            tasks.stop_background_tasks()
        finally:
            configure_source_caller(None)

    def test_actual_audio_watcher_accepts_stop_without_a_final_route_write(self):
        module = ast.parse((self.patched / DEVICE_COMMON).read_text())
        function = next(item for item in ast.walk(module) if isinstance(item, ast.FunctionDef) and item.name == "watch_audio_route")
        calls = []
        class StopAtWait:
            def is_set(self):
                return False
            def wait(self, timeout):
                calls.append(("wait", timeout))
                return True
        namespace = {"PyUiConfig": SimpleNamespace(get_usb_audio_route_path=lambda: "/never-read"),
                     "Path": lambda _: self.fail("Stopped audio watcher read a route"),
                     "time": SimpleNamespace(sleep=lambda _: self.fail("Stop-aware watcher used blocking sleep"))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<actual cooperative audio watcher>", "exec"), namespace)
        device = SimpleNamespace(_usb_audio_supported=lambda: True,
                                 _refresh_audio_route=lambda **_: self.fail("Stopped audio watcher reopened audio"))
        namespace["watch_audio_route"](device, StopAtWait())
        self.assertEqual(calls, [("wait", 1)])

    def test_actual_audio_watcher_retains_the_classic_no_argument_behavior(self):
        module = ast.parse((self.patched / DEVICE_COMMON).read_text())
        function = next(item for item in ast.walk(module) if isinstance(item, ast.FunctionDef) and item.name == "watch_audio_route")
        calls = []
        class FinishedFixture(Exception):
            pass
        def refresh(**kwargs):
            calls.append(("refresh", kwargs))
            raise FinishedFixture()
        namespace = {"PyUiConfig": SimpleNamespace(get_usb_audio_route_path=lambda: "/fixture-route"),
                     "Path": lambda _: SimpleNamespace(read_text=lambda: "fixture route"),
                     "time": SimpleNamespace(sleep=lambda seconds: calls.append(("sleep", seconds)))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<actual classic audio watcher>", "exec"), namespace)
        with self.assertRaises(FinishedFixture):
            namespace["watch_audio_route"](SimpleNamespace(_usb_audio_supported=lambda: True, _refresh_audio_route=refresh))
        self.assertEqual(calls, [("sleep", 1), ("refresh", {"reopen": True})])

    def test_caller_is_after_existing_main_menu_and_never_collects_a_return(self):
        text = (self.patched / MAINUI).read_text()
        self.assertLess(text.index("main_menu = MainMenu()"), text.index("project_tasks = start_background_threads()"))
        self.assertLess(text.index("project_tasks = start_background_threads()"), text.index("bind_source_session(main_menu, project_tasks)"))
        self.assertNotIn("collect_return", text)
        self.assertNotIn("clear_foreground", text)
        self.assertNotIn("menus/main_menu.py", {item["path"] for item in self.record["transformed"]})
        observed = next(item for item in self.audit["sources"] if item["path"] == MAINUI)
        self.assertEqual(hashlib.sha256((SOURCE / MAINUI).read_bytes()).hexdigest(), observed["sha256"])


if __name__ == "__main__":
    unittest.main()
