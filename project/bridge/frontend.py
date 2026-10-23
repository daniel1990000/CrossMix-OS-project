"""Select a frontend before optional project view imports execute.

The caller supplies lazy factories. This helper never launches spruce scripts
and never interprets a saved executable context as an action capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from psp_shell.health import FrontendHealth
from psp_shell.runtime import ContractError


@dataclass
class FrontendInstance:
    mode: str
    attempt_id: str
    instance: Any
    health: FrontendHealth

    def ready(self, *, first_frame: bool, input_ready: bool, settings_ready: bool):
        return self.health.mark_ready(first_frame=first_frame, input_ready=input_ready,
                                      settings_ready=settings_ready, attempt_id=self.attempt_id)


def load_frontend(health: FrontendHealth, *, classic_factory: Callable[[], Any],
                  project_factory: Callable[[], Any],
                  release_failed_frontend: Callable[[], bool]) -> FrontendInstance:
    """Allow one classic fallback only after verified cleanup of failed UI.

    Factories must be lazy: importing optional project views before calling
    this function would bypass the force-classic recovery contract.
    """
    selected = health.begin(health.choose_interface())
    mode, token = selected["attempt"]["interface"], selected["attempt"]["id"]
    factories = {"classic": classic_factory, "project": project_factory}
    try:
        return FrontendInstance(mode, token, factories[mode](), health)
    except Exception as exc:
        try:
            clean = release_failed_frontend() is True
        except Exception:
            clean = False
        if not clean:
            # Do not open another owner just because an import or constructor
            # failed after it may have acquired SDL/audio/input resources.
            raise ContractError("UI_RELEASE_UNCERTAIN", "Failed frontend resources are not known to be released; fallback is blocked") from exc
        record = health.note_failure(attempt_id=token)
        if mode == "classic" or record["blocked"]:
            raise ContractError("NO_SAFE_FRONTEND", "The classic frontend failed; offline repair is required") from exc
        fallback = health.begin("classic")
        token = fallback["attempt"]["id"]
        try:
            return FrontendInstance("classic", token, classic_factory(), health)
        except Exception as fallback_error:
            # The caller may log a redacted error; this module does not start
            # a third UI or try a firmware/Flip-only fallback.
            try:
                release_failed_frontend()
            finally:
                health.note_failure(attempt_id=token)
            raise ContractError("NO_SAFE_FRONTEND", "The classic frontend also failed; offline repair is required") from fallback_error
