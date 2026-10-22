"""Host-only transactional settings checks using disposable files."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from psp_shell.settings import SettingsError, SettingsStore, SpruceConfigTransaction
from psp_shell import settings


class TemporarySettings(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assertCode(self, code, callback):
        with self.assertRaises(SettingsError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)


class SettingsTransactions(TemporarySettings):
    def store(self, **kwargs):
        return SettingsStore(self.root / "state", **kwargs)

    def apply(self, store, changes, request="apply-one"):
        generation = store.get()["generation"]
        preview = store.preview({"changes": changes, "expected_generation": generation})
        return store.apply({"preview_id": preview["preview_id"], "request_id": request,
                            "expected_generation": generation})

    def test_preview_apply_idempotence_and_interface_is_only_a_preference(self):
        store = self.store()
        original = store.target.read_bytes()
        preview = store.preview({"changes": {"confirm": "east", "interface": "project"}, "expected_generation": 0})
        self.assertEqual(store.target.read_bytes(), original)
        request = {"preview_id": preview["preview_id"], "request_id": "request-1", "expected_generation": 0}
        result = store.apply(request)
        self.assertEqual(result["generation"], 1)
        self.assertEqual(result["preferences"]["confirm"], "east")
        self.assertEqual(result["preferences"]["interface"], "project")
        again = store.apply(request)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["transaction_id"], result["transaction_id"])
        self.assertFalse((self.root / "runtrimui.sh").exists())
        other = store.preview({"changes": {"sound": False}, "expected_generation": 1})
        self.assertCode("IDEMPOTENCY_CONFLICT", lambda: store.apply(
            {"preview_id": other["preview_id"], "request_id": "request-1", "expected_generation": 1}))

    def test_stale_generation_and_same_generation_external_edit(self):
        store = self.store()
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})
        self.apply(store, {"motion": False})
        self.assertCode("STALE_GENERATION", lambda: store.apply(
            {"preview_id": preview["preview_id"], "request_id": "late", "expected_generation": 0}))
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 1})
        state = json.loads(store.target.read_text())
        state["preferences"]["text_scale"] = 1.5
        store.target.write_text(json.dumps(state))
        before = store.target.read_bytes()
        self.assertCode("STALE_SNAPSHOT", lambda: store.apply(
            {"preview_id": preview["preview_id"], "request_id": "external", "expected_generation": 1}))
        self.assertEqual(store.target.read_bytes(), before)

    def test_undo_only_owned_keys_preserves_unrelated_external_edits(self):
        store = self.store()
        result = self.apply(store, {"sound": False})
        state = json.loads(store.target.read_text())
        state["preferences"]["text_scale"] = 1.5
        state["future_metadata"] = {"keep": [1, 2, 3]}
        store.target.write_text(json.dumps(state))
        undo = {"transaction_id": result["transaction_id"], "request_id": "undo-1", "expected_generation": 1}
        reverted = store.undo(undo)
        self.assertTrue(reverted["preferences"]["sound"])
        self.assertEqual(reverted["preferences"]["text_scale"], 1.5)
        self.assertEqual(json.loads(store.target.read_text())["future_metadata"], {"keep": [1, 2, 3]})
        self.assertTrue(store.undo(undo)["idempotent"])

    def test_undo_conflict_keeps_later_user_value(self):
        store = self.store()
        result = self.apply(store, {"sound": False})
        state = json.loads(store.target.read_text())
        state["preferences"]["sound"] = True
        store.target.write_text(json.dumps(state))
        before = store.target.read_bytes()
        self.assertCode("UNDO_CONFLICT", lambda: store.undo(
            {"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1}))
        self.assertEqual(store.target.read_bytes(), before)

    def test_bounds_unknown_fields_and_future_schema_fail_closed(self):
        store = self.store()
        for change in ({"text_scale": True}, {"text_scale": 10**1000}, {"motion": "false"},
                       {"text_scale": float("nan")}, {"confirm": []}):
            self.assertCode("INVALID_SETTING", lambda change=change: store.preview(
                {"changes": change, "expected_generation": 0}))
        self.assertCode("UNSUPPORTED_SETTING", lambda: store.preview(
            {"changes": {"input_player1_a": "different"}, "expected_generation": 0}))
        self.assertCode("UNKNOWN_FIELD", lambda: store.preview(
            {"changes": {"sound": False}, "expected_generation": 0, "command": "sh"}))
        state = json.loads(store.target.read_text())
        state["schema"] = 99
        store.target.write_text(json.dumps(state))
        before = store.target.read_bytes()
        self.assertCode("UNSUPPORTED_SCHEMA", store.get)
        self.assertEqual(store.target.read_bytes(), before)

    def test_duplicate_json_and_symlink_are_never_reset(self):
        store = self.store()
        store.target.write_bytes(b'{"schema":1,"schema":2,"generation":0,"preferences":{}}')
        before = store.target.read_bytes()
        self.assertCode("INVALID_CONFIG", store.get)
        self.assertEqual(store.target.read_bytes(), before)
        store.target.unlink()
        victim = self.root / "unowned.json"
        victim.write_text("keep me")
        store.target.symlink_to(victim)
        self.assertCode("UNSAFE_PATH", store.get)
        self.assertEqual(victim.read_text(), "keep me")

    def test_write_failure_rolls_back_and_reports_full_storage(self):
        store = self.store()
        original = store.target.read_bytes()
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})
        real_write = settings._atomic_write

        def disk_full(path, data, mode=None):
            if path == store.target:
                raise SettingsError("STORAGE_FULL", "fixture full disk")
            return real_write(path, data, mode)

        with mock.patch.object(settings, "_atomic_write", side_effect=disk_full):
            self.assertCode("STORAGE_FULL", lambda: store.apply(
                {"preview_id": preview["preview_id"], "request_id": "full", "expected_generation": 0}))
        self.assertEqual(store.target.read_bytes(), original)
        self.assertEqual(self.store().get()["generation"], 0)

    def test_read_only_file_is_not_bypassed_by_rename(self):
        store = self.store()
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})
        before = store.target.read_bytes()
        store.target.chmod(0o444)
        try:
            self.assertCode("STORAGE_READ_ONLY", lambda: store.apply(
                {"preview_id": preview["preview_id"], "request_id": "readonly", "expected_generation": 0}))
        finally:
            store.target.chmod(0o600)
        self.assertEqual(store.target.read_bytes(), before)

    def test_faults_before_commit_rollback_and_after_commit_retry_is_idempotent(self):
        for fault_point in ("prepared", "before_replace", "after_replace", "before_commit"):
            with self.subTest(point=fault_point):
                directory = self.root / fault_point
                store = SettingsStore(directory)
                before = store.target.read_bytes()
                preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})

                def interrupt(point, index, expected=fault_point):
                    if point == expected:
                        raise RuntimeError("synthetic interruption")

                broken = SettingsStore(directory, fault_hook=interrupt)
                with self.assertRaises(RuntimeError):
                    broken.apply({"preview_id": preview["preview_id"], "request_id": fault_point, "expected_generation": 0})
                self.assertEqual(SettingsStore(directory).target.read_bytes(), before)
        directory = self.root / "after-commit"
        store = SettingsStore(directory)
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})

        def lost_response(point, index):
            if point == "after_commit":
                raise RuntimeError("response lost after durable commit")

        request = {"preview_id": preview["preview_id"], "request_id": "lost-response", "expected_generation": 0}
        with self.assertRaises(RuntimeError):
            SettingsStore(directory, fault_hook=lost_response).apply(request)
        result = SettingsStore(directory).apply(request)
        self.assertTrue(result["idempotent"])
        self.assertEqual(result["generation"], 1)

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX crash fixture")
    def test_process_death_after_replace_is_recovered_before_read(self):
        store = self.store()
        before = store.target.read_bytes()
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})
        pid = os.fork()
        if pid == 0:
            broken = self.store(fault_hook=lambda point, index: os._exit(73) if point == "after_replace" else None)
            broken.apply({"preview_id": preview["preview_id"], "request_id": "crash", "expected_generation": 0})
            os._exit(99)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 73)
        self.assertNotEqual(store.target.read_bytes(), before)
        recovered = self.store()
        self.assertEqual(recovered.target.read_bytes(), before)
        self.assertEqual(recovered.get()["generation"], 0)

    def test_external_edit_blocks_recovery_without_overwriting_it(self):
        store = self.store()
        preview = store.preview({"changes": {"sound": False}, "expected_generation": 0})

        def interrupt(point, index):
            if point == "after_replace":
                current = json.loads(store.target.read_text())
                current["external"] = "keep"
                store.target.write_text(json.dumps(current))
                raise RuntimeError("fixture interruption")

        broken = self.store(fault_hook=interrupt)
        self.assertCode("RECOVERY_CONFLICT", lambda: broken.apply(
            {"preview_id": preview["preview_id"], "request_id": "conflict", "expected_generation": 0}))
        external = store.target.read_bytes()
        self.assertCode("RECOVERY_CONFLICT", store.recover)
        self.assertEqual(store.target.read_bytes(), external)


class SpruceSelections(TemporarySettings):
    def setUp(self):
        super().setUp()
        self.target = self.root / "spruce-config.json"
        self.data = {"unknown": {"keep": True}, "menuOptions": {
            "Test Settings": {
                "one": {"selected": "Off", "options": ["Off", "On"], "changeCmd": "never executed"},
                "two": {"selected": "Off", "options": ["Off", "On"]},
                "other_device": {"selected": "Off", "options": ["Off", "On"], "devices": ["TRIMUI_SMART_PRO_S"]},
                "password": {"selected": "", "type": "freeText"},
            }}}
        self.target.write_text(json.dumps(self.data))
        self.effects = {"one": "Off", "two": "Off"}
        self.calls = []

    def backend(self, change):
        self.calls.append(copy.deepcopy(change))
        self.effects[change["key"]] = change["after"]
        return True

    def adapter(self, **kwargs):
        return SpruceConfigTransaction(self.target, self.root / "state", quiescent=lambda: True,
                                       backend=self.backend, **kwargs)

    def preview(self, adapter, *keys):
        return adapter.preview({"changes": [{"category": "Test Settings", "key": key, "value": "On"}
                                            for key in keys], "expected_generation": 0})

    def test_snapshot_and_preview_do_not_write_authoritative_selection(self):
        before = self.target.read_bytes()
        adapter = self.adapter()
        adapter.snapshot()
        preview = self.preview(adapter, "one")
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.calls, [])
        result = adapter.apply({"preview_id": preview["preview_id"], "request_id": "one", "expected_generation": 0})
        self.assertEqual(result["generation"], 1)
        self.assertEqual(json.loads(self.target.read_text())["menuOptions"]["Test Settings"]["one"]["selected"], "On")
        self.assertEqual(json.loads(self.target.read_text())["unknown"], {"keep": True})

    def test_backend_failure_compensates_and_keeps_all_old_selections(self):
        adapter = self.adapter()
        preview = self.preview(adapter, "one", "two")
        before = self.target.read_bytes()

        def fail_second(change):
            self.backend(change)
            return not (change["key"] == "two" and change["after"] == "On")

        adapter.backend = fail_second
        self.assertCode("BACKEND_FAILED", lambda: adapter.apply(
            {"preview_id": preview["preview_id"], "request_id": "failure", "expected_generation": 0}))
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.effects, {"one": "Off", "two": "Off"})
        self.assertEqual(adapter.snapshot()["generation"], 0)

    def test_failed_compensation_is_a_truthful_pending_recovery(self):
        adapter = self.adapter()
        preview = self.preview(adapter, "one")
        before = self.target.read_bytes()
        adapter.backend = lambda change: False
        self.assertCode("BACKEND_RECONCILE_REQUIRED", lambda: adapter.apply(
            {"preview_id": preview["preview_id"], "request_id": "unreconciled", "expected_generation": 0}))
        self.assertEqual(self.target.read_bytes(), before)
        adapter.backend = self.backend
        adapter.recover()
        self.assertEqual(self.effects["one"], "Off")

    def test_backend_observes_old_selection_and_never_receives_command_text(self):
        adapter = self.adapter()
        preview = self.preview(adapter, "one")

        def explicit(change):
            self.assertEqual(set(change), {"category", "key", "before", "after"})
            self.assertEqual(json.loads(self.target.read_text())["menuOptions"]["Test Settings"]["one"]["selected"], "Off")
            return self.backend(change)

        adapter.backend = explicit
        adapter.apply({"preview_id": preview["preview_id"], "request_id": "explicit", "expected_generation": 0})

    def test_undo_compensates_only_owned_option_preserving_external_fields(self):
        adapter = self.adapter()
        preview = self.preview(adapter, "one")
        result = adapter.apply({"preview_id": preview["preview_id"], "request_id": "apply", "expected_generation": 0})
        data = json.loads(self.target.read_text())
        data["external"] = ["retain"]
        self.target.write_text(json.dumps(data))
        request = {"transaction_id": result["transaction_id"], "request_id": "undo", "expected_generation": 1}
        adapter.undo(request)
        self.assertEqual(self.effects["one"], "Off")
        self.assertEqual(json.loads(self.target.read_text())["external"], ["retain"])
        self.assertTrue(adapter.undo(request)["idempotent"])

    def test_device_and_free_text_and_busy_writer_gates(self):
        adapter = self.adapter()
        for key, code in (("other_device", "UNSUPPORTED_SETTING"), ("password", "INVALID_SETTING")):
            self.assertCode(code, lambda key=key: self.preview(adapter, key))
        preview = self.preview(adapter, "one")
        adapter.quiescent = lambda: False
        self.assertCode("BUSY_WRITER", lambda: adapter.apply(
            {"preview_id": preview["preview_id"], "request_id": "busy", "expected_generation": 0}))
        self.assertEqual(self.calls, [])

    def test_malformed_device_options_fail_without_backend_actions(self):
        adapter = self.adapter()
        data = json.loads(self.target.read_text())
        data["menuOptions"]["Test Settings"]["one"]["options"] = "On"
        self.target.write_text(json.dumps(data))
        self.assertCode("INVALID_CONFIG", lambda: self.preview(adapter, "one"))
        self.assertEqual(self.calls, [])

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX crash fixture")
    def test_crash_after_backend_is_compensated_on_recovery(self):
        effect_file = self.root / "backend-value"
        effect_file.write_text("Off")

        def persistent_backend(change):
            effect_file.write_text(change["after"])
            return True

        adapter = self.adapter()
        adapter.backend = persistent_backend
        preview = self.preview(adapter, "one")
        pid = os.fork()
        if pid == 0:
            adapter.fault_hook = lambda point, index: os._exit(74) if point == "after_backend" else None
            adapter.apply({"preview_id": preview["preview_id"], "request_id": "crash", "expected_generation": 0})
            os._exit(99)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 74)
        self.assertEqual(effect_file.read_text(), "On")
        adapter.recover()
        self.assertEqual(effect_file.read_text(), "Off")
        self.assertEqual(adapter.snapshot()["generation"], 0)


if __name__ == "__main__":
    unittest.main()
