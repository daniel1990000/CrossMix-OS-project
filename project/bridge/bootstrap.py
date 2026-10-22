"""Original trusted binding for an already initialized, qualified PyUI session.

No saved metadata selects callbacks, no upstream managers are initialized here,
and no process/display/input owner is started. The source integration supplies
its lifecycle authorities and independent live observations explicitly.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError, SPRUCE_COMMIT


PRINCIPAL_PATH = "spruce/scripts/principal.sh"


@dataclass(frozen=True)
class ExistingPyUIModels:
    """References to the existing models, not constructor names or imports."""

    system_manager: Any
    game_list: Callable[[str], Any]
    favorites_manager: Any
    recents_manager: Any
    label_for: Callable[[Any], str] | None = None
    artwork_for: Callable[[Any], str | None] | None = None

    def assert_ready(self) -> None:
        if not callable(getattr(self.system_manager, "get_active_systems", None)) or not callable(self.game_list):
            raise ContractError("MODELS_NOT_READY", "Already initialized PyUI system and ROM models are required")
        for manager, getter in ((self.favorites_manager, "get_favorites"), (self.recents_manager, "get_recents")):
            event = getattr(manager, "_init_event", None)
            if not callable(getattr(manager, getter, None)) or event is None or not event.is_set():
                raise ContractError("MODELS_NOT_READY", "The existing PyUI history managers have not finished startup")

    def provider(self, sd_root, **kwargs):
        self.assert_ready()
        from psp_shell.adapters.spruce import PyUIModelProvider
        return PyUIModelProvider(sd_root, system_manager=self.system_manager, game_list=self.game_list,
            favorites_manager=self.favorites_manager, recents_manager=self.recents_manager,
            label_for=self.label_for, artwork_for=self.artwork_for, **kwargs)


@dataclass(frozen=True)
class ForegroundIdentity:
    token: str
    request_id: str
    boot_id: str
    generation: int

    @classmethod
    def from_health(cls, health: FrontendHealth) -> "ForegroundIdentity | None":
        value = health.foreground_identity()
        return None if value is None else cls(**value)


@dataclass(frozen=True)
class SpruceReturnEvidence:
    """A trusted source-owner observation; never deserialize this from a file.

    The qualified source seam must independently establish process completion
    and staged-command consumption. A callback returning after staging, an
    image, or an exit code alone does not satisfy this contract. This receipt
    says nothing about successful save/state operations.
    """

    foreground: ForegroundIdentity
    source_commit: str
    principal_sha256: str
    staged_command_absent: bool
    foreground_ended: bool
    verification_id: str


class InitializedPyUIBinding:
    """Capture existing authorities and bind a lazy, refreshable context.

    ``profile`` is copied from independently qualified expected evidence.
    ``inventory`` and ``preferences`` observe the current session on every
    preflight, including launch and advanced routes. Do not populate expected
    hashes from those observations. All device gates still apply in the runner.
    """

    def __init__(self, *, device: Any, display: Any, controller: Any,
                 models: ExistingPyUIModels, state_dir: str | Path,
                 profile: Mapping[str, Any], inventory: Callable[[], Mapping[str, Any]],
                 preferences: Callable[[], Mapping[str, Any]], quiescent: Callable[[], bool],
                 stop_background_tasks: Callable[[], None], restore_background_tasks: Callable[[], None],
                 release_input: Callable[[], None], restore_input: Callable[[], None],
                 sd_root: str | Path = "/mnt/SDCARD", execution_environment: str = "device",
                 current_owners: Callable[[], tuple[Any, Any, Any]] | None = None,
                 verify_return: Callable[[ForegroundIdentity], SpruceReturnEvidence] | None = None,
                 tool_list: Callable | None = None, tool_actions: Mapping | None = None,
                 mode_actions: Mapping | None = None, report_error: Callable[[str], None] | None = None,
                 font_provider: Callable | None = None, control_adapter: Any = None,
                 theme_manager: Any = None):
        required = (inventory, preferences, quiescent, stop_background_tasks, restore_background_tasks,
                    release_input, restore_input)
        if not isinstance(profile, Mapping) or not isinstance(models, ExistingPyUIModels) or any(not callable(value) for value in required):
            raise ContractError("INVALID_CONTEXT", "Binding requires explicit live evidence, existing models and paired lifecycle callbacks")
        if ((current_owners is not None and not callable(current_owners)) or
                (verify_return is not None and not callable(verify_return))):
            raise ContractError("INVALID_CONTEXT", "Owner and return checks must be trusted in-process callbacks")
        self.device, self.display, self.controller = device, display, controller
        self.models, self.state_dir, self.sd_root = models, Path(state_dir).resolve(), sd_root
        self._profile = copy.deepcopy(dict(profile))
        self.inventory, self.preferences, self.quiescent = inventory, preferences, quiescent
        self.current_owners, self.verify_return = current_owners, verify_return
        self.report_error = report_error
        self.execution_environment = execution_environment
        self.options = dict(stop_background_tasks=stop_background_tasks,
            restore_background_tasks=restore_background_tasks, release_input=release_input,
            restore_input=restore_input, tool_list=tool_list, tool_actions=tool_actions,
            mode_actions=mode_actions, report_error=report_error, font_provider=font_provider,
            control_adapter=control_adapter, theme_manager=theme_manager)
        self._assert_owners()

    def _assert_owners(self):
        if self.current_owners is not None:
            current = self.current_owners()
            if not isinstance(current, tuple) or len(current) != 3 or any(a is not b for a, b in zip(current, (self.device, self.display, self.controller))):
                raise ContractError("OWNER_CHANGED", "PyUI replaced an initialized authority; rebuild the trusted binding")
        checks = ((self.device, ("run_game",)),
                  (self.display, ("present",)),
                  (self.controller, ("get_input", "still_held_down", "clear_input_queue", "clear_last_input", "last_input")))
        if any(not callable(getattr(owner, name, None)) for owner, names in checks for name in names):
            raise ContractError("INVALID_CONTEXT", "The existing PyUI device/display/controller must already be initialized")
        if getattr(getattr(self.display, "renderer", None), "renderer", None) is None or getattr(getattr(self.display, "window", None), "window", None) is None:
            raise ContractError("DISPLAY_UNAVAILABLE", "The existing PyUI renderer and window must already exist")

    def _assert_session(self):
        self._assert_owners()
        self.models.assert_ready()

    def _live_inventory(self):
        self._assert_session()
        value = self.inventory()
        self._assert_session()
        return value

    def _live_preferences(self):
        self._assert_session()
        value = self.preferences()
        self._assert_session()
        return value

    def __call__(self, main_menu):
        self._assert_session()
        if self.quiescent() is not True:
            raise ContractError("BUSY_SESSION", "Existing startup and foreground work must be idle before binding the project view")
        from psp_shell.embedded import EmbeddedContext
        return EmbeddedContext(self.sd_root, self.state_dir, self.device, self.display, self.controller,
            main_menu, {}, copy.deepcopy(self._profile), {}, self.quiescent,
            execution_environment=self.execution_environment, inventory_provider=self._live_inventory,
            preferences_provider=self._live_preferences, model_provider_factory=self.models.provider,
            assert_owners=self._assert_session,
            **self.options)

    def bind(self):
        from .pyui_entry import bind_context_factory
        bind_context_factory(self, state_dir=self.state_dir)
        return self

    def collect_return(self, main_menu, *, health: FrontendHealth | None = None) -> SpruceReturnEvidence | None:
        """Only a verified spruce owner seam may explicitly request collection.

        Generic frontend startup never calls this automatically. The pinned
        base still needs a separately qualified principal return integration.
        Failed, stale, untyped or cross-boot observations retain the tombstone.
        """
        health = health or FrontendHealth(self.state_dir)
        if health.directory.resolve() != self.state_dir:
            raise ContractError("INVALID_CONTEXT", "Return evidence belongs to another frontend state directory")
        expected = ForegroundIdentity.from_health(health)
        if expected is None:
            return None
        if expected.boot_id != health.boot_id or self.verify_return is None:
            raise ContractError("RETURN_UNVERIFIED", "A qualified same-boot spruce return authority is required")
        from psp_shell.embedded import qualification
        context = self(main_menu)
        qualification(context).assert_safe()
        evidence = self.verify_return(expected)
        digest = self._profile.get("required_hashes", {}).get(PRINCIPAL_PATH)
        if (type(evidence) is not SpruceReturnEvidence or evidence.foreground != expected or
            evidence.source_commit != SPRUCE_COMMIT or not isinstance(digest, str) or
            re.fullmatch(r"[0-9a-f]{64}", digest) is None or evidence.principal_sha256 != digest or
            evidence.staged_command_absent is not True or evidence.foreground_ended is not True or
            not isinstance(evidence.verification_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}", evidence.verification_id) is None):
            raise ContractError("RETURN_UNVERIFIED", "Spruce return evidence does not match the independently qualified ownership contract")
        # Refresh after the source authority as well; it must not qualify a
        # changed runtime or leave another staged action/foreground operation.
        qualification(context).assert_safe()
        if self.quiescent() is not True or ForegroundIdentity.from_health(health) != expected:
            raise ContractError("STALE_HANDOFF", "The foreground or idle session changed while verifying its return")
        health.clear_foreground(expected.token, verified=True, expected_generation=expected.generation)
        return evidence


def bind_running_pyui(**kwargs) -> InitializedPyUIBinding:
    """Use fixed imports of existing owners; never initialize their singletons.

    The reviewed source bootstrap calls this after its normal initialization,
    passing existing model references and qualified lifecycle authorities. No
    installed source hook calls it and no shipped profile is enabled by it.
    """
    from devices.device import Device
    from display.display import Display
    from controller.controller import Controller
    owners = lambda: (Device.get_device(), Display, Controller)
    device, display, controller = owners()
    return InitializedPyUIBinding(device=device, display=display, controller=controller,
        current_owners=owners, **kwargs).bind()
