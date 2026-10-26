# SPDX-License-Identifier: MIT
"""Private source integration acceptance; no installed card or device is used.

SourceUseReview values here are explicit host fixtures. They are never evidence
of a real notification, permission, physical qualification or distributable OS.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integration import release as integration

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))


class ReleaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / "App/PyUI/main-ui/menus/main_menu.py").is_file():
            raise unittest.SkipTest("Set SPRUCE_SOURCE_ROOT to the complete pinned host reference")
        cls.inventory = integration.source_inventory(SOURCE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="integration-acceptance-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for item in integration.source_inventory(SOURCE, include_state_session=True):
            destination = self.source / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((SOURCE / item["path"]).read_bytes())
        self.review = integration.SourceUseReview(integration.overlay.SPRUCE_COMMIT,
                                                  "host-fixture-only:not-a-real-notification")

    def assembled(self, name="candidate", **kwargs):
        output = self.root / name
        record = integration.assemble_private_candidate(self.source, output, source_review=self.review,
                                                        bridge_mode="none", **kwargs)
        return output, record

    def rewrite_manifest(self, output, change):
        path = output / "candidate.json"
        record = json.loads(path.read_text())
        record.pop("checksum")
        change(record)
        path.write_bytes(integration.overlay.canonical(integration.overlay.record_with_checksum(record)) + b"\n")

    def signed_original(self, name, *, full=False):
        payload = self.root / (name + "-payload")
        if full:
            sys.path.insert(0, str(PROJECT / "tools"))
            from build_payload import build_payload
            build_payload(PROJECT, payload)
        else:
            (payload / "app/psp_shell").mkdir(parents=True)
            (payload / integration.overlay.ENTRYPOINT).write_text("print('host fixture')\n")
        public, secret = integration.overlay.Sodium().keypair()
        key, private = self.root / (name + "-public"), self.root / (name + "-private")
        key.write_bytes(public)
        private.write_bytes(secret)
        profile = integration.overlay.read_json(PROJECT / "packaging/profiles/spruce454-tg5040-development.json")
        archive = self.root / (name + ".tar")
        integration.overlay.create_archive(payload, archive, private, key, profile, name, "python-extension")
        return archive, key

    def test_prepare_retains_exact_patch_and_notice_scope_without_source_derivation(self):
        output = self.root / "review"
        original = integration.source_inventory(self.source)
        record = integration.prepare_review_kit(self.source, output)
        self.assertEqual(integration.verify_candidate(output), record)
        self.assertEqual(integration.source_inventory(self.source), original)
        self.assertFalse((output / "tree").exists())
        self.assertFalse(record["source_derived"])
        self.assertFalse(record["source_use_reviewed"])
        self.assertEqual(len(record["patches"]), 4)
        self.assertEqual(len(list((output / "notices").iterdir())), 3)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)

    def test_all_four_actual_source_patches_assemble_and_restore_in_new_outputs(self):
        original = integration.source_inventory(self.source)
        output, record = self.assembled()
        self.assertEqual(len(record["changes"]), 4)
        self.assertEqual(integration.verify_candidate(output), record)
        for item in record["changes"]:
            self.assertEqual(hashlib.sha256((output / "tree" / item["path"]).read_bytes()).hexdigest(), item["after_sha256"])
            self.assertEqual((output / "backup" / item["path"]).read_bytes(), (self.source / item["path"]).read_bytes())
        restore = self.root / "restored"
        restored = integration.restore_private_candidate(output, restore)
        self.assertEqual(integration.verify_candidate(restore), restored)
        self.assertEqual(restored["kind"], "private-source-restoration")
        for item in restored["changes"]:
            self.assertEqual((restore / "tree" / item["path"]).read_bytes(), (self.source / item["path"]).read_bytes())
        self.assertEqual(integration.source_inventory(self.source), original)
        self.assertEqual(integration.verify_candidate(output), record)

    def test_json_or_boolean_review_cannot_produce_a_derivative(self):
        for review in (None, True, {"source_use_verified": True},
                       integration.SourceUseReview("b" * 40, "fixture-only")):
            with self.subTest(review=review), self.assertRaises(integration.IntegrationError):
                integration.assemble_private_candidate(self.source, self.root / "unapproved", source_review=review)
        self.assertFalse((self.root / "unapproved").exists())

    def test_source_drift_and_patch_result_drift_abort_before_publication(self):
        name = self.inventory[0]["path"]
        (self.source / name).write_bytes(b"drift\n")
        with self.assertRaises(integration.IntegrationError):
            self.assembled()
        self.assertFalse((self.root / "candidate").exists())
        (self.source / name).write_bytes((SOURCE / name).read_bytes())
        patches = integration._locked_patches()
        patches[0]["data"] = patches[0]["data"].replace(b"+import shlex", b"+import math")
        with patch.object(integration, "_locked_patches", return_value=patches):
            with self.assertRaisesRegex(integration.IntegrationError, "locked result"):
                self.assembled()
        self.assertFalse((self.root / "candidate").exists())

    def test_mid_assembly_source_changes_abort_and_leave_no_partial_output(self):
        def change(root, staging, mode):
            name = next(item["path"] for item in integration._locked_patches())
            (self.source / name).write_bytes(b"changed during trusted stage callback\n")
            return [], None
        with patch.object(integration, "_bridge_patch", side_effect=change):
            with self.assertRaisesRegex(integration.IntegrationError, "changed after inventory"):
                self.assembled()
        self.assertFalse((self.root / "candidate").exists())
        self.assertFalse(any(path.name.startswith(".integration-assembly-") for path in self.root.iterdir()))

    def test_changed_candidate_backup_or_patch_refuses_restore_without_overwriting(self):
        output, record = self.assembled()
        target = output / "tree" / record["changes"][0]["path"]
        target.write_bytes(b"later edit retained\n")
        with self.assertRaises(integration.IntegrationError):
            integration.restore_private_candidate(output, self.root / "refused")
        self.assertFalse((self.root / "refused").exists())
        self.assertEqual(target.read_bytes(), b"later edit retained\n")

    def test_recomputed_manifest_cannot_relabel_a_changed_backup_as_a_pinned_preimage(self):
        output, record = self.assembled()
        item = record["changes"][0]
        backup = output / "backup" / item["path"]
        backup.write_bytes(b"This is a later edit, not the original pinned source.\n")
        changed_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
        def relabel(value):
            value["artifact_files"] = integration._artifact_inventory(output)
            next(change for change in value["changes"] if change["path"] == item["path"])["before_sha256"] = changed_hash
        self.rewrite_manifest(output, relabel)
        with self.assertRaisesRegex(integration.IntegrationError, "pinned source preimage"):
            integration.restore_private_candidate(output, self.root / "forged-restoration")
        self.assertFalse((self.root / "forged-restoration").exists())
        self.assertEqual(backup.read_bytes(), b"This is a later edit, not the original pinned source.\n")

    def test_recomputed_manifest_cannot_omit_locked_source_scope(self):
        output = self.root / "review-missing-observation"
        integration.prepare_review_kit(self.source, output)
        self.rewrite_manifest(output, lambda value: value["source_inventory"].pop())
        with self.assertRaisesRegex(integration.IntegrationError, "omits a locked integration preimage"):
            integration.verify_candidate(output)
        candidate, record = self.assembled("candidate-missing-patch-target")
        item = record["changes"][0]
        (candidate / "tree" / item["path"]).unlink()
        (candidate / "backup" / item["path"]).unlink()
        def omit_result(value):
            value["changes"].pop(0)
            value["installation"] = integration._installation(value["changes"], "none")
            value["artifact_files"] = integration._artifact_inventory(candidate)
        self.rewrite_manifest(candidate, omit_result)
        with self.assertRaisesRegex(integration.IntegrationError, "complete source scope"):
            integration.verify_candidate(candidate)

    def test_private_artifact_cannot_claim_hardware_clearance_even_with_valid_checksum(self):
        output, record = self.assembled()
        for field in ("hardware_qualified", "runtime_verified", "distribution_cleared", "device_activation"):
            self.rewrite_manifest(output, lambda value: value.update({field: True}))
            with self.subTest(field=field), self.assertRaisesRegex(integration.IntegrationError, "mint qualification"):
                integration.verify_candidate(output)
            self.rewrite_manifest(output, lambda value: value.update({field: False}))
        self.assertEqual(integration.verify_candidate(output), record)
        self.rewrite_manifest(output, lambda value: value["installation"]["targets"][0].update(card_relative_path="Emu/PSP/PPSSPPSDL"))
        with self.assertRaisesRegex(integration.IntegrationError, "fixed installation scope"):
            integration.verify_candidate(output)
        self.rewrite_manifest(output, lambda value: value.update(installation=record["installation"]))
        self.rewrite_manifest(output, lambda value: value.update(external_blockers=[]))
        with self.assertRaisesRegex(integration.IntegrationError, "external qualification"):
            integration.verify_candidate(output)

    def test_added_user_data_or_changed_licence_breaks_complete_inventory(self):
        output = self.root / "review"
        integration.prepare_review_kit(self.source, output)
        (output / "Saves").mkdir()
        (output / "Saves/owner-data").write_bytes(b"must never get packaged\n")
        with self.assertRaisesRegex(integration.IntegrationError, "inventory changed"):
            integration.verify_candidate(output)
        (output / "Saves/owner-data").unlink()
        (output / "notices/0-LICENSE").write_bytes(b"incorrect licence\n")
        self.rewrite_manifest(output, lambda value: value.update(artifact_files=integration._artifact_inventory(output)))
        with self.assertRaisesRegex(integration.IntegrationError, "upstream licence"):
            integration.verify_candidate(output)

    def test_ancestor_symlinks_and_nonregular_sources_are_refused(self):
        source = self.source / "App/PyUI/main-ui/menus/main_menu.py"
        original = source.read_bytes()
        source.unlink()
        outside = self.root / "outside.py"
        outside.write_bytes(original)
        source.symlink_to(outside)
        with self.assertRaises(OSError):
            integration.prepare_review_kit(self.source, self.root / "symlinked")
        source.unlink()
        os.mkfifo(source)
        with self.assertRaisesRegex(integration.IntegrationError, "regular file"):
            integration.prepare_review_kit(self.source, self.root / "fifo")
        self.assertFalse((self.root / "fifo").exists())

    def test_output_must_be_new_separate_and_never_replaces_an_existing_tree(self):
        for output in (self.source / "inside", self.source, self.root):
            with self.subTest(output=output), self.assertRaises((ValueError, OSError)):
                integration.prepare_review_kit(self.source, output)
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "owner-data"
        sentinel.write_text("retain")
        with self.assertRaises(integration.IntegrationError):
            integration.prepare_review_kit(self.source, existing)
        self.assertEqual(sentinel.read_text(), "retain")

    def test_signed_original_overlay_keeps_separate_trust_and_never_mints_device_gates(self):
        archive, key = self.signed_original("integration-test")
        output = self.root / "with-original"
        record = integration.prepare_review_kit(self.source, output, overlay_archive=archive, public_key=key)
        self.assertFalse(record["original_overlay"]["grants_source_or_hardware_qualification"])
        self.assertEqual(integration.verify_candidate(output, public_key=key), record)
        with self.assertRaisesRegex(integration.IntegrationError, "external trusted"):
            integration.verify_candidate(output)
        other, _ = integration.overlay.Sodium().keypair()
        wrong = self.root / "wrong-public"
        wrong.write_bytes(other)
        with self.assertRaises(ValueError):
            integration.prepare_review_kit(self.source, self.root / "bad-signature", overlay_archive=archive, public_key=wrong)
        self.assertFalse((self.root / "bad-signature").exists())

    def test_actual_process_boundary_composes_with_all_reliability_fixes_and_original_modules(self):
        archive, key = self.signed_original("process-fixture", full=True)
        output = self.root / "process-candidate"
        record = integration.assemble_private_candidate(self.source, output, source_review=self.review,
            bridge_mode="process-exit", overlay_archive=archive, public_key=key, include_state_session=True)
        self.assertEqual(record["bridge_review"]["module_root"], integration.MODULE_ROOT)
        self.assertFalse(record["bridge_review"]["requires_legacy_lifecycle_hook"])
        self.assertEqual(len(record["patches"]), 6)
        self.assertTrue(record["include_state_session"])
        self.assertEqual(integration.verify_candidate(output, public_key=key), record)
        miyoo = (output / "tree/App/PyUI/main-ui/devices/miyoo_trim_common.py").read_text()
        self.assertIn("import shlex", miyoo)
        self.assertIn("from bridge.process_source import stage_existing_command", miyoo)
        self.assertTrue((output / "tree" / integration.PAYLOAD_ROOT / "app/bridge/principal.py").is_file())
        self.assertTrue((output / "tree" / integration.PAYLOAD_ROOT / "assets/fonts/NotoSans.ttf").is_file())
        ui_modules = {"app/psp_shell/ui/" + path.name for path in (PROJECT / "psp_shell/ui").glob("*.py")}
        required = set(record["bridge_review"]["required_project_modules"])
        self.assertTrue(ui_modules <= required, ui_modules - required)
        from build_payload import PAYLOAD_TOOLS
        self.assertEqual(integration.SIGNED_TOOL_MODULES, {"app/tools/" + name for name in PAYLOAD_TOOLS})
        self.assertTrue(integration.SIGNED_TOOL_MODULES <= required)
        with integration.overlay.VerifiedArchive(archive, integration.overlay.load_key(key, 32)) as verified:
            signed = {item["path"]: item["sha256"] for item in verified.manifest["files"]}
        retained = {item["path"]: item["sha256"] for item in record["artifact_files"]}
        for relative in ("app/psp_shell/ui/motion.py", "app/psp_shell/ui/pictograms.py",
                         *sorted(integration.SIGNED_TOOL_MODULES)):
            expected = hashlib.sha256((PROJECT / relative.removeprefix("app/")).read_bytes()).hexdigest()
            self.assertEqual(signed[relative], expected)
            self.assertEqual(retained["tree/" + integration.PAYLOAD_ROOT + "/" + relative], expected)
        self.assertIn("TRIMUI_PROJECT_STATE_REQUEST", (output / "tree/spruce/scripts/emu/lib/ppsspp_functions.sh").read_text())
        restored = self.root / "process-restored"
        restore = integration.restore_private_candidate(output, restored, public_key=key)
        self.assertEqual(integration.verify_candidate(restored, public_key=key), restore)
        self.assertEqual((restored / "tree/App/PyUI/main-ui/devices/miyoo_trim_common.py").read_bytes(),
                         (self.source / "App/PyUI/main-ui/devices/miyoo_trim_common.py").read_bytes())

    def test_process_boundary_rejects_missing_or_stale_original_payload_before_publication(self):
        output = self.root / "process-rejected"
        with self.assertRaisesRegex(integration.IntegrationError, "verified original overlay"):
            integration.assemble_private_candidate(self.source, output, source_review=self.review)
        archive, key = self.signed_original("stale-original")
        with self.assertRaisesRegex(integration.IntegrationError, "stale or lacks"):
            integration.assemble_private_candidate(self.source, output, source_review=self.review,
                overlay_archive=archive, public_key=key)
        self.assertFalse(output.exists())

    def test_process_boundary_rejects_an_unapproved_tool_even_in_a_signed_archive(self):
        from bridge import principal_integration
        _, key = self.signed_original("tool-scope", full=True)
        payload = self.root / "tool-scope-payload"
        (payload / "app/tools/unapproved.py").write_text("# must remain outside the integration scope\n")
        archive = self.root / "extra-tool.tar"
        profile = integration.overlay.read_json(PROJECT / "packaging/profiles/spruce454-tg5040-development.json")
        integration.overlay.create_archive(payload, archive, self.root / "tool-scope-private", key,
                                           profile, "extra-tool", "python-extension")
        output = self.root / "tool-scope-refused"
        with patch.object(principal_integration, "REQUIRED_PROJECT_MODULES",
                          principal_integration.REQUIRED_PROJECT_MODULES + ["app/tools/unapproved.py"]):
            with self.assertRaisesRegex(integration.IntegrationError, "outside the signed original app scope"):
                integration.assemble_private_candidate(self.source, output, source_review=self.review,
                    overlay_archive=archive, public_key=key)
        self.assertFalse(output.exists())

    def test_recomputed_private_inventory_cannot_replace_an_expanded_signed_module(self):
        archive, key = self.signed_original("modified-expanded-original", full=True)
        output = self.root / "changed-original-module"
        integration.assemble_private_candidate(self.source, output, source_review=self.review,
            overlay_archive=archive, public_key=key)
        for name in ("app/bridge/principal.py", "app/psp_shell/ui/motion.py", "app/psp_shell/ui/pictograms.py",
                     "app/tools/backup_catalog.py", "app/tools/recovery_payload.py"):
            with self.subTest(module=name):
                module = output / "tree" / integration.PAYLOAD_ROOT / name
                original = module.read_bytes()
                module.write_bytes(b"raise RuntimeError('modified outside the verified original payload')\n")
                self.rewrite_manifest(output, lambda value: value.update(artifact_files=integration._artifact_inventory(output)))
                with self.assertRaisesRegex(integration.IntegrationError, "differs from its signed payload"):
                    integration.verify_candidate(output, public_key=key)
                module.write_bytes(original)

    def test_optional_state_session_is_retained_only_when_explicitly_selected(self):
        default = integration.prepare_review_kit(self.source, self.root / "default-state-off")
        opted = integration.prepare_review_kit(self.source, self.root / "state-review", include_state_session=True)
        self.assertFalse(default["include_state_session"])
        self.assertEqual(len(default["patches"]), 4)
        self.assertTrue(opted["include_state_session"])
        self.assertEqual(len(opted["patches"]), 5)
        self.assertEqual(integration.verify_candidate(self.root / "state-review"), opted)
        self.assertFalse(opted["device_activation"])

    def test_composed_candidate_source_principal_state_store_and_next_source_resume(self):
        from integration.host_flow_fixture import MARKER, SYNTHETIC_ENGINE
        fixture = self.root / "composed-flow"
        fixture.mkdir(mode=0o700)
        (fixture / ".host-flow-fixture").write_bytes(MARKER)
        archive, key = self.signed_original("composed-flow-source", full=True)
        candidate = fixture / "candidate"
        integration.assemble_private_candidate(self.source, candidate, source_review=self.review,
            bridge_mode="process-exit", include_state_session=True, overlay_archive=archive, public_key=key)
        card = fixture / "card"
        shutil.copytree(candidate / "tree", card)
        for relative in ("Emu/PSP", "Roms/PSP", "Saves/fixture-state", "App/PyUI", "spruce/scripts/emu"):
            (card / relative).mkdir(parents=True, exist_ok=True)
        (fixture / "private/transport").mkdir(parents=True, mode=0o700)
        game = card / "Roms/PSP/Fixture ü ; data.iso"
        game.write_bytes(b"Synthetic owner ROM identity; not game data.\n")
        (card / "Saves/fixture-state/native.ini").write_text("[General]\nSyntheticFixture = True\n")
        engine = card / "Emu/PSP/PPSSPPSDL_TrimUI"
        engine.write_text(SYNTHETIC_ENGINE.replace("__PYTHON__", sys.executable))
        engine.chmod(0o700)
        (card / "Emu/PSP/config.json").write_text(json.dumps({"label": "Fixture PSP", "devices": ["TRIMUI_A133P"],
            "launch": "../../spruce/scripts/emu/standard_launch.sh", "extlist": "iso", "default_emulator": "PPSSPP",
            "menuOptions": {"Emulator_64": {"devices": ["TRIMUI_A133P"], "options": ["PPSSPP"],
                "selected": "PPSSPP", "overrides": {}}}}))
        driver = PROJECT / "integration/host_flow_fixture.py"
        source_launcher = card / "App/PyUI/launch.sh"
        source_launcher.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(str(value)) for value in
            (sys.executable, driver, fixture, "source")) + "\n")
        source_launcher.chmod(0o700)
        radio_launcher = card / "spruce/scripts/wifi.sh"
        radio_launcher.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(str(value)) for value in
            (sys.executable, driver, fixture, "resident-worker")) + "\n")
        # The actual patched run_ppsspp body and argument forwarding execute.
        # All hardware/config/screenshot services below are explicit fixtures.
        text = (card / "spruce/scripts/emu/lib/ppsspp_functions.sh").read_text()
        body = "run_ppsspp() {" + text.split("run_ppsspp() {", 1)[1].split("\nconfigure_retroachievements()", 1)[0]
        hardware = '/mnt/SDCARD/spruce/scripts/asound-setup.sh "$HOME"'
        self.assertEqual(body.count(hardware), 1)
        body = body.replace(hardware, 'fixture_asound "$HOME"')
        setup = ["#!/bin/sh", "set -e", 'ROM_FILE="$1"', "PLATFORM=host-fixture",
            "EMU_DIR=" + shlex.quote(str(card / "Emu/PSP")), "PSP_BIN=" + shlex.quote(str(engine)),
            "PSP_SS_DIR=" + shlex.quote(str(fixture / "engine-shots")),
            "SS_DIR=" + shlex.quote(str(fixture / "frontend-shots")),
            "PSP_DIR=" + shlex.quote(str(fixture / "fixture-config")),
            "set_up_default_configs_if_needed() { :; }", "load_ppsspp_configs() { :; }",
            "configure_retroachievements() { :; }", "move_screenshots_if_present() { :; }",
            "mount() { :; }", "umount() { :; }", "fixture_asound() { :; }",
            "save_ppsspp_configs() { :; }", "vk_display_preload() { :; }",
            "emu_log_file() { printf '%s' " + shlex.quote(str(fixture / "engine.log")) + "; }",
            "log_message() { :; }", body, "run_ppsspp", ""]
        shared_launcher = card / "spruce/scripts/emu/standard_launch.sh"
        shared_launcher.write_text("\n".join(setup))
        shared_launcher.chmod(0o700)
        app = card / integration.PAYLOAD_ROOT / "app"
        environment = dict(os.environ, PYTHONPATH=str(app), PYTHONDONTWRITEBYTECODE="1",
            TRIMUI_PROJECT_STATE_REQUEST="/poisoned-global/request", TRIMUI_PROJECT_RESUME_STATE="/poisoned-global/state")
        outputs = []
        relay = subprocess.Popen([sys.executable, str(driver), str(fixture), "resident"], cwd=fixture,
                                 env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        source_environment = dict(environment, TRIMUI_PROJECT_RESIDENT_SERVER=str(relay.pid))
        try:
            for operation in ("resident-ready", "pyui", "command", "pyui", "command", "inspect"):
                result = subprocess.run([sys.executable, str(driver), str(fixture), operation], cwd=fixture,
                                        env=source_environment, capture_output=True, text=True, timeout=20)
                debug = (fixture / "engine.log").read_text() if (fixture / "engine.log").is_file() else ""
                self.assertEqual(result.returncode, 0, result.stderr + "\n" + debug)
                if operation != "resident-ready":
                    outputs.append(json.loads(result.stdout))
            # Persistent shared-service fixtures remain the relay's children,
            # while both actual source and game subtrees already reached ECHILD.
            self.assertEqual(len(list(fixture.glob("resident-active-*"))), 2)
            self.assertIsNone(relay.poll())
            self.assertEqual([int(path.read_text()) for path in sorted(fixture.glob("resident-parent-*"))],
                             [relay.pid, relay.pid])
        finally:
            (fixture / "resident-release").write_text("allow explicit synthetic services to finish")
            try:
                drain = subprocess.run([sys.executable, str(driver), str(fixture), "resident-drain"], cwd=fixture,
                                       env=source_environment, capture_output=True, text=True, timeout=10)
                self.assertEqual(drain.returncode, 0, drain.stderr)
                _, error = relay.communicate(timeout=10)
                self.assertEqual(relay.returncode, 0, error)
            finally:
                if relay.poll() is None:
                    relay.kill()  # failed-fixture cleanup, never a service-stop claim
                    relay.communicate(timeout=5)
        self.assertEqual(len(list(fixture.glob("resident-descendant-*"))), 2)
        self.assertFalse(list(fixture.glob("resident-active-*")))
        self.assertTrue(outputs[-1]["saved_capability"])
        self.assertTrue(outputs[-1]["load_acknowledgement"])
        self.assertTrue(outputs[-1]["foreground_clear"])
        self.assertTrue(all(value["children_reaped"] >= 3 for value in outputs[:-1]))
        self.assertEqual(outputs[0]["import_root"], str(app))
        save = json.loads((fixture / "engine-save.json").read_text())
        resume = json.loads((fixture / "engine-resume.json").read_text())
        self.assertNotEqual(save["request"], resume["request"])
        self.assertEqual(save["resume_state"], "")
        self.assertTrue(resume["resume_state"].endswith("engine-owned-slot.ppst"))
        self.assertIn("--state=" + resume["resume_state"], resume["arguments"])
        self.assertNotIn("poisoned-global", save["request"] + resume["request"] + resume["resume_state"])
        self.assertTrue((fixture / "display-released").exists())
        self.assertTrue((fixture / "engine-descendant-save").exists())
        self.assertTrue((fixture / "engine-descendant-resume").exists())
        self.assertFalse((fixture / "cmd_to_run.sh").exists())
        self.assertEqual(integration.verify_candidate(candidate, public_key=key)["hardware_qualified"], False)

    def test_cli_has_no_source_use_override_install_or_activate_switch(self):
        command = [sys.executable, "-m", "integration.release"]
        env = dict(os.environ, PYTHONPATH=str(PROJECT))
        for action in ("install", "activate", "assemble"):
            self.assertNotEqual(subprocess.run(command + [action], env=env, capture_output=True).returncode, 0)
        output = self.root / "cli-review"
        result = subprocess.run(command + ["prepare", "--source-root", str(self.source), "--output", str(output)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["device_activation"])


if __name__ == "__main__":
    unittest.main()
