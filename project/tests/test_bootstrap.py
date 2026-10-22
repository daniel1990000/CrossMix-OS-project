"""Original injected bootstrap/return contracts; no physical qualification."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from bridge.bootstrap import (ExistingPyUIModels, ForegroundIdentity,
                              InitializedPyUIBinding, PRINCIPAL_PATH,
                              SpruceReturnEvidence, bind_running_pyui)
from bridge.pyui_entry import bind_context_factory, maybe_run_main_menu
from psp_shell.embedded import qualification
from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError, POWER_OFF_ROUTE, SPRUCE_COMMIT


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(bind_context_factory, None)
        self.directory = Path(self.temporary.name)
        self.events = []
        self.ready = threading.Event()
        self.ready.set()
        self.device = SimpleNamespace(run_game=lambda _: None)
        self.display = SimpleNamespace(renderer=SimpleNamespace(renderer=object()),
            window=SimpleNamespace(window=object()), present=lambda: None)
        self.controller = SimpleNamespace(get_input=lambda **_: False, still_held_down=lambda: False,
            clear_input_queue=lambda: None, clear_last_input=lambda: None, last_input=lambda: None)
        self.favorites = SimpleNamespace(_init_event=self.ready, get_favorites=lambda: [])
        self.recents = SimpleNamespace(_init_event=self.ready, get_recents=lambda: [])
        self.models = ExistingPyUIModels(SimpleNamespace(get_active_systems=lambda: []),
            lambda _: [], self.favorites, self.recents)
        self.profile = {"source_use_verified": True, "hardware_qualified": True, "runtime_verified": True,
            "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1",
            "required_hashes": {PRINCIPAL_PATH: "a" * 64}}
        # Deliberately injected observations/profile flags exercise checks;
        # they are not recorded as live device observations anywhere.
        self.observed = {"model": "TG5040", "platform": "SmartPro", "architecture": "aarch64",
            "source_commit": SPRUCE_COMMIT, "firmware_version": "1.1.1", "live": True,
            "hashes": {PRINCIPAL_PATH: "a" * 64}}
        self.preferences = {"enableButtonWatchers": False, "poweroffCmd": POWER_OFF_ROUTE}
        self.menu = SimpleNamespace()

    def binding(self, **overrides):
        def inventory():
            self.events.append("observe-runtime")
            return self.observed
        def preferences():
            self.events.append("observe-preferences")
            return self.preferences
        kwargs = dict(device=self.device, display=self.display, controller=self.controller,
            models=self.models, state_dir=self.directory / "state", sd_root=self.directory / "card",
            profile=self.profile, inventory=inventory, preferences=preferences, quiescent=lambda: True,
            stop_background_tasks=lambda: self.events.append("stop"),
            restore_background_tasks=lambda: self.events.append("restore"),
            release_input=lambda: self.events.append("release-input"),
            restore_input=lambda: self.events.append("restore-input"))
        kwargs.update(overrides)
        return InitializedPyUIBinding(**kwargs)

    def evidence(self, identity):
        return SpruceReturnEvidence(identity, SPRUCE_COMMIT, "a" * 64, True, True, "fixture-return:1")

    def test_binding_reuses_existing_owners_and_refreshes_independent_evidence(self):
        binding = self.binding()
        context = binding(self.menu)
        self.assertIs(context.device, self.device)
        self.assertIs(context.display, self.display)
        self.assertIs(context.controller, self.controller)
        self.assertEqual(self.events, [])
        qualification(context).assert_safe()
        qualification(context).assert_safe()
        self.assertEqual(self.events, ["observe-runtime", "observe-preferences"] * 2)
        self.observed["hashes"][PRINCIPAL_PATH] = "b" * 64
        self.profile["required_hashes"][PRINCIPAL_PATH] = "b" * 64
        with self.assertRaises(ContractError) as caught:
            qualification(context).assert_safe()
        self.assertEqual(caught.exception.code, "RUNTIME_HASH_MISMATCH")
        self.assertEqual(context.profile["required_hashes"][PRINCIPAL_PATH], "a" * 64)

    def test_current_preference_change_cannot_reuse_initial_qualification(self):
        context = self.binding()(self.menu)
        qualification(context).assert_safe()
        self.preferences["enableButtonWatchers"] = True
        with self.assertRaises(ContractError) as caught:
            qualification(context).assert_safe()
        self.assertEqual(caught.exception.code, "UNSAFE_POWER_PREFERENCES")

    def test_bound_source_hook_stays_classic_while_existing_models_start(self):
        self.ready.clear()
        errors = []
        binding = self.binding(report_error=errors.append).bind()
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        health.request("project", 0)
        with patch("psp_shell.embedded.EmbeddedRunner") as runner:
            self.assertFalse(maybe_run_main_menu(self.menu, health=health))
            runner.assert_not_called()
        self.assertEqual(errors, ["MODELS_NOT_READY"])
        self.assertIsNone(health.record()["attempt"])

    def test_classic_selection_does_not_construct_the_optional_context(self):
        binding = self.binding().bind()
        self.ready.clear()
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        self.assertFalse(maybe_run_main_menu(self.menu, health=health))
        self.assertEqual(self.events, [])

    def test_model_adapter_wraps_existing_references_without_from_pyui(self):
        context = self.binding()(self.menu)
        kwargs = dict(device=self.device, release_resources=lambda: None, quiescent=lambda: True)
        with patch("psp_shell.adapters.spruce.PyUIModelProvider") as provider:
            context.model_provider_factory(context.sd_root, **kwargs)
        self.assertIs(provider.call_args.kwargs["system_manager"], self.models.system_manager)
        self.assertIs(provider.call_args.kwargs["favorites_manager"], self.favorites)
        self.assertIs(provider.call_args.kwargs["recents_manager"], self.recents)
        provider.from_pyui.assert_not_called()

    def test_owner_replacement_and_missing_lifecycle_callbacks_are_refused(self):
        current = [self.device, self.display, self.controller]
        binding = self.binding(current_owners=lambda: tuple(current))
        current[0] = SimpleNamespace(run_game=lambda _: None)
        with self.assertRaises(ContractError) as caught:
            binding(self.menu)
        self.assertEqual(caught.exception.code, "OWNER_CHANGED")
        with self.assertRaises(ContractError):
            self.binding(restore_input=None)
        with self.assertRaises(ContractError):
            self.binding(inventory=self.observed)

    def test_owner_replacement_after_context_creation_invalidates_next_preflight(self):
        current = [self.device, self.display, self.controller]
        context = self.binding(current_owners=lambda: tuple(current))(self.menu)
        qualification(context).assert_safe()
        current[0] = SimpleNamespace(run_game=lambda _: None)
        with self.assertRaises(ContractError) as caught:
            qualification(context).assert_safe()
        self.assertEqual(caught.exception.code, "OWNER_CHANGED")

    def test_equivalent_state_paths_accept_the_same_return_record(self):
        binding = self.binding(state_dir=self.directory / "other" / ".." / "state",
            verify_return=self.evidence)
        health = FrontendHealth(self.directory / "state", boot_id="fixture")
        health.begin_foreground("fixture-game")
        self.assertIsNotNone(binding.collect_return(self.menu, health=health))

    def test_observation_failure_and_missing_return_authority_cannot_clear_foreground(self):
        def failed_inventory():
            raise RuntimeError("injected live inventory failure")
        binding = self.binding(inventory=failed_inventory, verify_return=self.evidence)
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        health.begin_foreground("fixture-game")
        before = health.foreground.read_bytes()
        with self.assertRaises(RuntimeError):
            binding.collect_return(self.menu, health=health)
        self.assertEqual(health.foreground.read_bytes(), before)
        binding = self.binding()
        with self.assertRaises(ContractError) as caught:
            binding.collect_return(self.menu, health=health)
        self.assertEqual(caught.exception.code, "RETURN_UNVERIFIED")
        self.assertEqual(health.foreground.read_bytes(), before)

    def test_fixed_running_entry_only_reads_existing_singletons(self):
        import sys
        modules = {
            "devices": SimpleNamespace(),
            "devices.device": SimpleNamespace(Device=SimpleNamespace(get_device=lambda: self.device)),
            "display": SimpleNamespace(), "display.display": SimpleNamespace(Display=self.display),
            "controller": SimpleNamespace(), "controller.controller": SimpleNamespace(Controller=self.controller),
        }
        original = self.binding()
        kwargs = dict(models=self.models, state_dir=original.state_dir, profile=self.profile,
            inventory=original.inventory, preferences=original.preferences, quiescent=original.quiescent,
            **{name: original.options[name] for name in ("stop_background_tasks", "restore_background_tasks", "release_input", "restore_input")})
        with patch.dict(sys.modules, modules):
            binding = bind_running_pyui(**kwargs)
            context = binding(self.menu)
        self.assertEqual(context.sd_root, "/mnt/SDCARD")
        self.assertIs(context.device, self.device)
        self.assertEqual(self.events, [])

    def test_readonly_foreground_identity_and_successful_source_return(self):
        binding = self.binding(verify_return=self.evidence)
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        token = health.begin_foreground("fixture-game")
        first = health.foreground_identity()
        before = health.foreground.read_bytes()
        first["token"] = "mutated-copy"
        self.assertEqual(health.foreground.read_bytes(), before)
        self.assertEqual(health.foreground_identity()["token"], token)
        result = binding.collect_return(self.menu, health=health)
        self.assertEqual(result.foreground.token, token)
        self.assertIsNone(health.foreground_identity())
        health.assert_no_foreground()
        self.assertEqual(self.events.count("observe-runtime"), 2)

    def test_incomplete_untyped_stale_and_crossboot_return_evidence_preserve_tombstone(self):
        variants = (
            lambda identity: self.evidence(identity).__dict__,
            lambda identity: replace(self.evidence(identity), foreground_ended=False),
            lambda identity: replace(self.evidence(identity), staged_command_absent=False),
            lambda identity: replace(self.evidence(identity), principal_sha256="b" * 64),
            lambda identity: replace(self.evidence(identity), foreground=replace(identity, request_id="another-game")),
        )
        for index, verify in enumerate(variants):
            with self.subTest(index=index):
                binding = self.binding(state_dir=self.directory / str(index), verify_return=verify)
                health = FrontendHealth(binding.state_dir, boot_id="fixture")
                health.begin_foreground("fixture-game")
                before = health.foreground.read_bytes()
                with self.assertRaises(ContractError) as caught:
                    binding.collect_return(self.menu, health=health)
                self.assertEqual(caught.exception.code, "RETURN_UNVERIFIED")
                self.assertEqual(health.foreground.read_bytes(), before)
        binding = self.binding(verify_return=self.evidence)
        health = FrontendHealth(binding.state_dir, boot_id="old-boot")
        health.begin_foreground("fixture-game")
        health.boot_id = "new-boot"
        with self.assertRaises(ContractError):
            binding.collect_return(self.menu, health=health)
        self.assertIsNotNone(health.foreground_identity())

    def test_runtime_change_during_return_verification_is_refused(self):
        def verify(identity):
            self.observed["hashes"][PRINCIPAL_PATH] = "b" * 64
            return self.evidence(identity)
        binding = self.binding(verify_return=verify)
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        health.begin_foreground("fixture-game")
        with self.assertRaises(ContractError) as caught:
            binding.collect_return(self.menu, health=health)
        self.assertEqual(caught.exception.code, "RUNTIME_HASH_MISMATCH")
        self.assertIsNotNone(health.foreground_identity())

    def test_replaced_foreground_during_return_verification_is_not_cleared(self):
        binding = self.binding()
        health = FrontendHealth(binding.state_dir, boot_id="fixture")
        health.begin_foreground("fixture-game")
        def verify(identity):
            health.clear_foreground(identity.token, verified=True)
            health.begin_foreground("fixture-new-game")
            return self.evidence(identity)
        binding.verify_return = verify
        with self.assertRaises(ContractError) as caught:
            binding.collect_return(self.menu, health=health)
        self.assertEqual(caught.exception.code, "STALE_HANDOFF")
        self.assertEqual(health.foreground_identity()["request_id"], "fixture-new-game")


if __name__ == "__main__":
    unittest.main()
