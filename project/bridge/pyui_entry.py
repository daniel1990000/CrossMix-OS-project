"""Source-fork entry seam; default behavior is the untouched classic menu.

A qualified bootstrap binds an in-memory context factory after existing PyUI
initialization. Metadata never supplies an import path, callback or command.
This module can select classic without importing optional presentation code.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError, SPRUCE_COMMIT


DEFAULT_STATE = "/mnt/SDCARD/App/PSPMode/state"
MAIN_MENU_PATH = "App/PyUI/main-ui/menus/main_menu.py"
MAIN_MENU_BLOB = "86ba5ccdba0be3453b6bddf1c24e9e91cec5c706"
_factory: Callable[[Any], Any] | None = None
_state_dir: str | Path = DEFAULT_STATE
_experimental_session = None


def bind_context_factory(factory: Callable[[Any], Any] | None, *, state_dir: str | Path = DEFAULT_STATE) -> None:
    """Called by trusted source bootstrap, never by a saved preference file."""
    if factory is not None and not callable(factory):
        raise ContractError("INVALID_CONTEXT", "A trusted in-process context factory is required")
    global _factory, _state_dir, _experimental_session
    _factory, _state_dir, _experimental_session = factory, state_dir, None


def bind_experimental_context_factory(factory, session, *, state_dir=DEFAULT_STATE):
    """Fixed reviewed code binds one typed private case after source startup."""
    from .experimental_runtime import ExperimentalRuntimeSession
    if type(session) is not ExperimentalRuntimeSession:
        raise ContractError("INVALID_CONTEXT", "Private source binding requires a typed reviewed session")
    session.assert_configuration(session._config)
    bind_context_factory(factory, state_dir=state_dir)
    global _experimental_session
    _experimental_session = session


def maybe_run_main_menu(main_menu: Any, *, context: Any = None, health: FrontendHealth | None = None,
                        dependencies: Any = None, max_frames: int = 0, scripted_actions=()) -> bool:
    """Return False to continue the existing MainMenu implementation.

    A future selector schema is left untouched and can use classic after the
    independent foreground-ownership record proves no same-boot uncertainty.
    No new Flip boot-session or firmware fallback is assumed.
    """
    experimental = getattr(context, "experimental_session", None) if context is not None else _experimental_session
    if experimental is not None:
        from .experimental_runtime import ExperimentalRuntimeSession
        if type(experimental) is not ExperimentalRuntimeSession:
            raise ContractError("INVALID_CONTEXT", "Private entry requires the fixed typed reviewed session")
    health = health or FrontendHealth(context.state_dir if context is not None else _state_dir)
    health.assert_no_foreground()
    try:
        selected = health.choose_interface()
    except ContractError as exc:
        if exc.code == "FUTURE_SCHEMA":
            return False
        raise
    if selected == "classic" and experimental is None:
        return False
    private_health = None
    if experimental is not None:
        private_health = health.record()
        if (private_health["attempt"] is not None or private_health["fallback_used"] or
                private_health["blocked"] or health.marker.exists()):
            raise ContractError("EXPERIMENTAL_RECOVERY_REQUIRED", "Existing frontend recovery must be resolved before a private case; its record is retained")
    if context is None:
        if _factory is None:
            return False
        try:
            context = _factory(main_menu)
        except ContractError as exc:
            if experimental is not None:
                experimental.block("identity_changed")
            # The trusted bootstrap only captures initialized references and
            # reads evidence. A not-yet-ready model or changed owner leaves
            # the current classic MainMenu available without loading views.
            report = getattr(_factory, "report_error", None)
            if callable(report):
                report(exc.code)
            return False
    # The recovery choice happened before this optional source adapter import.
    from psp_shell.embedded import EmbeddedRunner, qualification
    try:
        if Path(context.state_dir).resolve() != health.directory.resolve():
            raise ContractError("INVALID_CONTEXT", "Bound frontend state does not match the recovery selector")
        qualification(context).assert_safe()
    except ContractError as exc:
        if experimental is not None:
            experimental.block("identity_changed")
        if context.report_error:
            context.report_error(exc.code)
        return False
    if experimental is not None:
        if context.experimental_session is not experimental:
            raise ContractError("INVALID_CONTEXT", "The private context does not match its reviewed bound session")
        state = health.request("project", private_health["generation"])
        selected = "project"
        attempt = health.begin(selected, expected_generation=state["generation"])
    else:
        attempt = health.begin(selected)
    if attempt["attempt"]["interface"] == "classic":
        if experimental is not None:
            experimental.block()
        # begin detected an interrupted previous project startup. Classic's
        # own frame/input acceptance belongs to the source hook qualification;
        # do not fabricate a readiness receipt for it here.
        health.delegate_classic(attempt["attempt"]["id"])
        return False
    runner = EmbeddedRunner(context, health=health, attempt_id=attempt["attempt"]["id"],
                            dependencies=dependencies)
    try:
        result = runner.run(max_frames=max_frames, scripted_actions=scripted_actions)
        return result.reason != "classic"
    except SystemExit:
        # Normal existing device handoff: preserve process exit and ownership.
        raise
    except Exception as exc:
        if context.report_error:
            context.report_error(getattr(exc, "code", "EMBEDDED_START_FAILED"))
        if not runner.release_for_fallback():
            raise ContractError("UI_RELEASE_UNCERTAIN", "Project resources or foreground handoff are uncertain; a second UI is blocked") from exc
        if runner.ready:
            record = health.note_runtime_failure()
        else:
            record = health.note_failure(attempt_id=attempt["attempt"]["id"])
        if record["blocked"]:
            raise ContractError("NO_SAFE_FRONTEND", "The known classic fallback is not safe to restart") from exc
        # The existing MainMenu continues in its already initialized Display.
        # This is a selected fallback, not a claim that its first frame passed.
        return False


def stage_main_menu_hook(source_root: str | Path, staging_dir: str | Path, *,
                         source_use_verified: bool = False) -> dict[str, Any]:
    """Produce a reviewable patch in staging, never alter the upstream tree.

    The patch is inert until the qualified startup binds context_factory. The
    caller must resolve source-use obligations before deriving this artifact.
    Firmware/rootfs files, boot shims and existing patch manifests are excluded.
    """
    if source_use_verified is not True:
        raise ContractError("SOURCE_USE_UNVERIFIED", "Resolve the source-use obligations before producing a PyUI integration patch")
    root = Path(source_root).resolve(strict=True)
    source = root / MAIN_MENU_PATH
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 65536:
        raise ContractError("SOURCE_MISMATCH", "The pinned MainMenu source must be a bounded regular file")
    raw = source.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if digest != MAIN_MENU_BLOB:
        raise ContractError("SOURCE_MISMATCH", "MainMenu differs from the pinned spruce v4.5.4 source")
    staging = Path(staging_dir).absolute()
    try:
        staging.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise ContractError("UNSAFE_STAGING", "Integration staging must be outside the untouched source tree")
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    # Preserve game-selection-only mode and the base's pending GameSwitcher
    # and box-art work before taking over the main menu. Inserting at method
    # entry would silently skip those existing session-owner routes.
    marker = ("        self.check_for_gameswitcher()" + newline +
              "        self.check_for_boxart_resizing()" + newline)
    if text.count(marker) != 1:
        raise ContractError("SOURCE_MISMATCH", "The unique MainMenu seam could not be located")
    addition = ("        try:" + newline +
                "            from bridge.pyui_entry import maybe_run_main_menu" + newline +
                "        except (ImportError, SyntaxError):" + newline +
                "            maybe_run_main_menu = None" + newline +
                "        if maybe_run_main_menu is not None and maybe_run_main_menu(self):" + newline +
                "            return" + newline + newline)
    changed = text.replace(marker, marker + addition, 1)
    patch = "".join(difflib.unified_diff(text.splitlines(keepends=True), changed.splitlines(keepends=True),
                                       fromfile="a/" + MAIN_MENU_PATH, tofile="b/" + MAIN_MENU_PATH))
    if any(path.is_symlink() for path in (staging, *staging.parents)):
        raise ContractError("UNSAFE_STAGING", "Integration staging cannot contain symlink directories")
    staging.mkdir(parents=True, exist_ok=True)
    target = staging / "0001-pyui-main-menu-psp-seam.patch"
    metadata = staging / "integration-hook.json"
    if target.is_symlink() or metadata.is_symlink():
        raise ContractError("UNSAFE_STAGING", "Integration artifacts cannot replace symlinks")
    target.write_bytes(patch.encode("utf-8"))
    record = {"schema": 1, "base_commit": SPRUCE_COMMIT, "source_path": MAIN_MENU_PATH,
              "source_git_blob": digest, "patch_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "source_use_verified": True, "requires_qualified_context_binding": True,
              "hardware_execution_enabled": False, "modifies_rootfs_or_boot": False}
    metadata.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
