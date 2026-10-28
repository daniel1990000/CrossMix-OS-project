# SPDX-License-Identifier: MIT
"""Small per-game PPSSPP edits through the existing stopped-writer authority.

Game-to-INI associations come from the trusted installed config authority. Shell
IDs and ROM basenames are not PPSSPP disc IDs, so this module never guesses a
filename or creates a game override. PS1 continues to use its existing options.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import uuid

from .controls import (_configuration_bytes, _configuration_text, _ppsspp_assignment as _assignment,
                       _ppsspp_semantic_token as _semantic, _under,
                       set_ppsspp_config_token as _set_token)
from .ppsspp import PPSSPPExperienceManager
from .settings import (_Transactions, SettingsError, _atomic_write, _check_generation, _directory,
                       _encoded, _fields, _generation, _identifier, _json, _read, _require, _schema, _sha)


_INHERIT = {"value": None, "label": "Use current global setting",
            "description": "Remove this game's override now. PPSSPP may save the inherited value as this game's setting after play."}
OPTIONS = (
    {"id": "resolution", "key": "InternalResolution", "label": "Rendering resolution",
     "description": "Lower resolution reduces GPU work and image detail. It does not change intended game speed.",
     "choices": [_INHERIT,
                 {"value": 1, "label": "1x PSP", "description": "480 × 272 rendering; less detail and less GPU work."},
                 {"value": 2, "label": "2x PSP", "description": "960 × 544 rendering; sharper with more GPU work."},
                 {"value": 3, "label": "3x PSP", "description": "1440 × 816 rendering; more GPU work. Untested on Smart Pro."}]},
    {"id": "frameskip", "key": "FrameSkip", "label": "Manual frameskip",
     "description": "Skipping drawn frames can reduce GPU work, but makes motion less smooth. Turn automatic frameskip off first.",
     "choices": [_INHERIT,
                 {"value": 0, "label": "Off", "description": "Draw every game frame when the emulator can keep up."},
                 {"value": 1, "label": "Skip 1", "description": "Draw fewer frames; visible motion tradeoff. Untested."},
                 {"value": 2, "label": "Skip 2", "description": "Draw still fewer frames; larger motion tradeoff. Untested."}]},
    {"id": "auto_frameskip", "key": "AutoFrameSkip", "label": "Automatic frameskip",
     "description": "Let PPSSPP skip drawn frames as needed; pacing and motion can vary. Manual frameskip is inactive while this is on.",
     "choices": [_INHERIT,
                 {"value": False, "label": "Off", "description": "Use the manual frameskip setting."},
                 {"value": True, "label": "On", "description": "Let PPSSPP vary skipped frames. Requires Skip Buffer Effects to be off."}]},
)
_BY_ID = {option["id"]: option for option in OPTIONS}
PRESETS = (
    {"id": "native-resolution", "label": "Native-resolution candidate", "status": "untested",
     "description": "1x PSP resolution, no frameskip. Lower image detail; no performance gain is promised.",
     "changes": {"resolution": 1, "frameskip": 0, "auto_frameskip": False}},
    {"id": "higher-detail", "label": "Higher-detail candidate", "status": "untested",
     "description": "2x PSP resolution, no frameskip. More GPU work; requires game-and-scene measurement.",
     "changes": {"resolution": 2, "frameskip": 0, "auto_frameskip": False}},
)


def unavailable_status(game_id, system_id="PSP", reason="This installed game's PPSSPP configuration has not been verified."):
    """A readable catalog is not permission to write an installed configuration."""
    ps1 = str(system_id).casefold() in {"ps", "ps1", "psx", "playstation"}
    return {"schema": 1, "game_id": game_id, "generation": 0, "available": False, "writable": False,
            "gate_reason": "EXISTING_EMULATOR_OPTIONS" if ps1 else "UNQUALIFIED_PER_GAME_CONFIG",
            "reason": "Use this game's existing emulator options; the selected PS1 emulator is preserved." if ps1 else reason,
            "route": "game.options", "scope": "per-game", "candidate_status": "untested",
            "options": [] if ps1 else [{**copy.deepcopy(option), "value": None, "effective_value": None,
                                         "inherited": None, "value_available": False} for option in OPTIONS],
            "presets": [] if ps1 else copy.deepcopy(list(PRESETS)), "runtime_observed": False,
            "emulator_binary_changed": False}


def _value(option, found):
    if found is None:
        return None
    value = _semantic(found["token"], boolean=option["id"] == "auto_frameskip")
    _require(not isinstance(value, str) or len(value) <= 128, "INVALID_CONFIG", "An owned native performance value is malformed or too long")
    if option["id"] != "auto_frameskip" and isinstance(value, str) and re.fullmatch(r"[+-]?\d{1,10}", value):
        return int(value)
    return value


def _remove(text, key):
    found = _assignment(text, "Graphics", key)
    return text if found is None else text[:found["line_start"]] + text[found["line_end"]:]


def _changes(text, selections):
    _require(isinstance(selections, dict) and selections and set(selections) <= set(_BY_ID),
             "INVALID_ARGUMENT", "Choose supported native performance options")
    diff = []
    for option in OPTIONS:
        identifier, key = option["id"], option["key"]
        if identifier not in selections:
            continue
        value = selections[identifier]
        _require(any(type(value) is type(choice["value"]) and value == choice["value"] for choice in option["choices"]),
                 "INVALID_ARGUMENT", "Unknown value for a native performance option")
        found = _assignment(text, "Graphics", key)
        before = _value(option, found)
        if (found is None and value is None) or (found is not None and type(before) is type(value) and before == value):
            continue
        diff.append({"option_id": identifier, "label": option["label"], "section": "Graphics", "key": key,
                     "before_present": found is not None, "before_token": found["token"] if found else None,
                     "before": before, "after_present": value is not None, "after": value})
        if value is None:
            text = _remove(text, key)
        else:
            token = ("True" if value else "False") if type(value) is bool else str(value)
            text = _set_token(text, key, token, section="Graphics")
    return text, diff


class PPSSPPPerformanceManager:
    """Reuse PPSSPP's common lease, profile/inventory checks and rollback journal.

    ``game_configs`` is an explicit trusted mapping from stable shell game IDs to
    existing relative per-game INI paths in both qualified component inventories.
    A path can intentionally be shared by several content identities: PPSSPP
    itself keys these files by its game ID. Such aliases are reported to the UI.
    """

    def __init__(self, experience_manager, state_dir, *, game_configs, game_identity=None, fault_hook=None):
        _require(isinstance(experience_manager, PPSSPPExperienceManager), "INVALID_ARGUMENT",
                 "Use the existing PPSSPP settings authority")
        _require(isinstance(game_configs, dict) and len(game_configs) <= 100000,
                 "INVALID_ARGUMENT", "A trusted game-to-configuration map is required")
        _require(game_identity is None or callable(game_identity), "INVALID_ARGUMENT",
                 "The installed game identity observer must be a trusted callable")
        for game_id, path in game_configs.items():
            _identifier(game_id, "game ID")
            _require(isinstance(path, str) and len(path) <= 4096, "INVALID_ARGUMENT", "Invalid game configuration path")
        self.experience = experience_manager
        self.game_identity = game_identity
        self.game_configs = copy.deepcopy(game_configs)
        self.mapping_sha256 = _sha(_encoded(self.game_configs))
        self.state_dir = _directory(Path(state_dir))
        self.previews = _directory(self.state_dir / "previews")
        self.meta = self.state_dir / "generation.json"
        _require(self.meta not in {self.experience.meta, self.experience.controls.meta, self.experience.appearance.meta},
                 "UNSAFE_PATH", "Performance transactions need a separate state directory")
        self.fault_hook = fault_hook
        with self.experience._window():
            self.experience._recover()
            self._transactions().recover()
            if _read(self.meta, optional=True) is None:
                _atomic_write(self.meta, _encoded({"schema": 1, "generation": 0}))

    def _state(self):
        state = _json(self.meta)
        _schema(state)
        _generation(state.get("generation"))
        return state

    def _target(self, game_id, control):
        _identifier(game_id, "game ID")
        relative = self.game_configs.get(game_id)
        _require(relative is not None, "UNQUALIFIED_PER_GAME_CONFIG",
                 "The existing config authority has not mapped this game's native PPSSPP ID. Use native game settings first.")
        _require(relative in control.get("per_game_configs", []), "PER_GAME_INVENTORY_CHANGED",
                 "This game configuration is absent from the verified per-game inventory")
        path = _under(self.experience.controls.sd_root, relative)
        _require(path.parent == control["_config"].parent and path.name.endswith("_ppsspp.ini"),
                 "UNSAFE_PATH", "The game configuration is outside the verified PPSSPP directory")
        return relative, path

    def _identity(self, game_id, relative, control):
        _require(callable(self.game_identity), "UNQUALIFIED_GAME_IDENTITY",
                 "A live game-content, native ID and selected-emulator observation is required before editing this game.")
        try:
            identity = self.game_identity(game_id)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise SettingsError("GAME_IDENTITY_CHANGED", "Current game content or selected-emulator identity could not be observed") from error
        fields = {"native_game_id", "rom_sha256", "preset_id", "engine", "executable", "executable_sha256", "config_path"}
        _require(isinstance(identity, dict) and set(identity) == fields,
                 "UNQUALIFIED_GAME_IDENTITY", "The installed game identity observation is incomplete")
        native_id, rom_hash, preset = (identity.get(key) for key in ("native_game_id", "rom_sha256", "preset_id"))
        _require(isinstance(native_id, str) and bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", native_id)) and
                 Path(relative).name == native_id + "_ppsspp.ini" and identity.get("config_path") == relative and
                 isinstance(rom_hash, str) and bool(re.fullmatch(r"[a-f0-9]{64}", rom_hash)) and
                 isinstance(preset, str) and 0 < len(preset) <= 128 and not any(ord(character) < 32 for character in preset),
                 "UNQUALIFIED_GAME_IDENTITY", "Current game content or native PPSSPP ID does not identify this configuration")
        _require(identity.get("engine") == "ppsspp" and identity.get("executable") == control.get("executable") and
                 identity.get("executable_sha256") == control.get("executable_sha256"),
                 "GAME_IDENTITY_CHANGED", "The selected game emulator differs from this verified PPSSPP settings authority")
        return copy.deepcopy(identity)

    def _qualified(self, game_id, metadata=None):
        control, theme = self.experience._qualified(metadata)
        relative, path = self._target(game_id, control)
        identity = self._identity(game_id, relative, control)
        if metadata is not None:
            _require(metadata.get("mapping_sha256") == self.mapping_sha256 and
                     metadata.get("config_path") == relative and metadata.get("game_id") == game_id,
                     "STALE_SNAPSHOT", "The trusted game configuration association changed")
            _require(metadata.get("game_identity") == identity, "GAME_IDENTITY_CHANGED",
                     "Game content, native game ID or selected emulator/preset changed since this settings transaction")
        return control, theme, relative, path

    def _validate_journal(self, journal):
        metadata = journal.get("metadata", {})
        game_id = metadata.get("game_id")
        control, _ = self.experience._profiles()
        relative, path = self._target(game_id, control)
        _require(metadata.get("config_path") == relative and metadata.get("mapping_sha256") == self.mapping_sha256,
                 "INVALID_TRANSACTION", "The game configuration authority changed")
        _require([item["path"] for item in journal["files"]] == [str(path), str(self.meta)],
                 "UNSAFE_PATH", "Performance journal targets an unowned file")

    def _transactions(self):
        guard = lambda journal: self._qualified(journal["metadata"]["game_id"], journal["metadata"])
        return _Transactions(self.state_dir / "transactions", self._validate_journal, self.fault_hook,
                             lambda journal, _persist: guard(journal), guard)

    def _recover(self):
        self.experience._recover()
        self._transactions().recover()

    @staticmethod
    def _effective(text, global_text, key, boolean=False):
        found = _assignment(text, "Graphics", key) or _assignment(global_text, "Graphics", key)
        return _semantic(found["token"], boolean=boolean) if found else None

    def status(self, game_id):
        _identifier(game_id, "game ID")
        with self.experience._window():
            self._recover()
            response = unavailable_status(game_id)
            response["generation"] = self._state()["generation"]
            try:
                control, _, relative, path = self._qualified(game_id)
                text, global_text = _configuration_text(_read(path)), _configuration_text(_read(control["_config"]))
                options = []
                for option in OPTIONS:
                    local = _assignment(text, "Graphics", option["key"])
                    effective = local or _assignment(global_text, "Graphics", option["key"])
                    options.append({**copy.deepcopy(option), "value": _value(option, local),
                                    "effective_value": _value(option, effective), "inherited": local is None,
                                    "value_available": effective is not None})
                aliases = sorted(identifier for identifier, value in self.game_configs.items() if value == relative and identifier != game_id)
                response.update(available=True, writable=True, gate_reason="", reason="Changes apply only to this native per-game configuration. Candidates are untested.",
                                options=options, config_path=relative, shared_game_ids=aliases,
                                game_identity=self._identity(game_id, relative, control), game_identity_verified=True,
                                shared_config_warning="Other library entries share this PPSSPP game configuration." if aliases else "")
            except SettingsError as error:
                response.update(gate_reason=error.code, reason=str(error))
            return response

    def _plan(self, params):
        _fields(params, {"game_id", "changes", "expected_generation"}, {"game_id", "changes", "expected_generation"})
        generation = _check_generation(params, self._state())
        control, theme, relative, path = self._qualified(params["game_id"])
        before, global_raw = _read(path), _read(control["_config"])
        text, diff = _changes(_configuration_text(before), params["changes"])
        _require(diff, "NO_CHANGES", "This game's selected native options already match")
        global_text = _configuration_text(global_raw)
        automatic = self._effective(text, global_text, "AutoFrameSkip", True)
        if "auto_frameskip" in params["changes"] and automatic is True:
            _require(self._effective(text, global_text, "SkipBufferEffects", True) is not True,
                     "SETTING_CONFLICT", "Turn off Skip Buffer Effects in native game settings first. PPSSPP would otherwise change that existing setting.")
        if "resolution" in params["changes"] and params["changes"]["resolution"] is not None:
            _require(self._effective(text, global_text, "SoftwareRenderer", True) is not True and
                     self._effective(text, global_text, "SkipBufferEffects", True) is not True,
                     "SETTING_CONFLICT", "Rendering resolution is inactive with Software Rendering or Skip Buffer Effects. Review those settings in PPSSPP first.")
        if "frameskip" in params["changes"] and params["changes"]["frameskip"] is not None:
            _require(automatic is not True, "SETTING_CONFLICT", "Turn automatic frameskip off before selecting manual frameskip")
        record = {"schema": 1, "game_id": params["game_id"], "generation": generation,
                  "config_path": relative, "mapping_sha256": self.mapping_sha256,
                  "profile_id": control["id"], "theme_profile_id": theme["id"],
                  "game_identity": self._identity(params["game_id"], relative, control),
                  "control_profile_sha256": control["_profile_hash"], "theme_profile_sha256": theme["_profile_hash"],
                  "global_sha256": _sha(global_raw), "config_sha256": _sha(before),
                  "after_sha256": _sha(_configuration_bytes(text)), "per_game_configs": self.experience._overlays(control, theme),
                  "experience_generation": self.experience._state()["generation"],
                  "controls_generation": self.experience.controls._state()["generation"],
                  "appearance_generation": self.experience.appearance._state()["generation"],
                  "changes": copy.deepcopy(params["changes"]), "diff": diff}
        return record, (path, before, _configuration_bytes(text))

    def preview(self, params):
        with self.experience._window():
            self._recover()
            record, _ = self._plan(params)
            preview_id = "performance-preview-" + uuid.uuid4().hex
            _atomic_write(self.previews / (preview_id + ".json"), _encoded({**record, "preview_id": preview_id}))
            aliases = [identifier for identifier, value in self.game_configs.items()
                       if value == record["config_path"] and identifier != record["game_id"]]
            warnings = ["Candidate settings are untested until matched game-and-scene measurements are recorded."]
            if any(value is None for value in record["changes"].values()):
                warnings.append("Use current global setting removes the override now. PPSSPP may save the inherited value as this game's setting after play; later global changes may then no longer apply.")
            if aliases:
                warnings.append("Other library entries share this PPSSPP game configuration.")
            return {"preview_id": preview_id, "generation": record["generation"], "game_id": record["game_id"],
                    "diff": record["diff"], "warnings": warnings, "candidate_status": "untested",
                    "scope": "per-game", "runtime_observed": False, "emulator_binary_changed": False}

    def apply(self, params):
        _fields(params, {"preview_id", "request_id", "expected_generation"}, {"preview_id", "request_id", "expected_generation"})
        preview_id, request_id = (_identifier(params[name], name) for name in ("preview_id", "request_id"))
        with self.experience._window():
            self._recover()
            transactions = self._transactions()
            replay = transactions.replay(request_id, "apply", preview_id)
            if replay is not None:
                return replay
            record = _json(self.previews / (preview_id + ".json"))
            _schema(record)
            self._qualified(record.get("game_id"), record)
            current, (path, before, after) = self._plan({"game_id": record.get("game_id"), "changes": record.get("changes"),
                                                      "expected_generation": params["expected_generation"]})
            _require(record.get("preview_id") == preview_id and
                     _encoded({key: record.get(key) for key in current}) == _encoded(current),
                     "STALE_SNAPSHOT", "Game settings, profiles or override inventory changed after preview")
            generation = record["generation"]
            tx = "performance-tx-" + uuid.uuid4().hex
            result = {"transaction_id": tx, "game_id": record["game_id"], "generation": generation + 1,
                      "applied": True, "idempotent": False, "scope": "per-game", "candidate_status": "untested",
                      "runtime_observed": False, "emulator_binary_changed": False}
            transactions.commit(tx, request_id, "apply", preview_id,
                                [(path, before, after), (self.meta, _read(self.meta), _encoded({"schema": 1, "generation": generation + 1}))],
                                record, result)
            return result

    def undo(self, params):
        _fields(params, {"transaction_id", "request_id", "expected_generation"}, {"transaction_id", "request_id", "expected_generation"})
        original, request_id = (_identifier(params[name], name) for name in ("transaction_id", "request_id"))
        with self.experience._window():
            self._recover()
            transactions = self._transactions()
            replay = transactions.replay(request_id, "undo", original)
            if replay is not None:
                return replay
            journal = transactions.journal(original)
            _require(journal["status"] == "committed" and journal.get("operation") == "apply",
                     "INVALID_TRANSACTION", "Only a committed native performance change can be undone")
            metadata = journal["metadata"]
            control, _, _, path = self._qualified(metadata["game_id"], metadata)
            generation = _check_generation(params, self._state())
            _require(journal["result"]["generation"] == generation, "UNDO_CONFLICT",
                     "Another performance transaction has followed this change")
            before = transactions.snapshot(journal, 0)
            applied = transactions.snapshot(journal, 0, True)
            expected, diff = _changes(_configuration_text(before), metadata.get("changes"))
            _require(_configuration_bytes(expected) == applied and _encoded(diff) == _encoded(metadata.get("diff")),
                     "UNDO_CONFLICT", "The saved performance change differs from its supported edits")
            current = _read(path)
            text, applied_text = _configuration_text(current), _configuration_text(applied)
            before_text = _configuration_text(before)
            for item in diff:
                option = _BY_ID[item["option_id"]]
                found = _assignment(text, "Graphics", item["key"])
                _require((found is not None) == item["after_present"] and
                         (found is None or (type(_value(option, found)) is type(item["after"]) and _value(option, found) == item["after"])),
                         "UNDO_CONFLICT", "An owned performance setting changed outside this transaction")
                if item["before_present"]:
                    text = _set_token(text, item["key"], item["before_token"], section="Graphics")
                    if not item["after_present"]:
                        # Inherit removed the entire owned line. Reinsert its
                        # original spelling and comment, keeping later owner
                        # edits elsewhere rather than replacing the whole INI.
                        original_line = _assignment(before_text, "Graphics", item["key"])
                        inserted = _assignment(text, "Graphics", item["key"])
                        line = before_text[original_line["line_start"]:original_line["line_end"]]
                        if not line.endswith(("\n", "\r")):
                            inserted_line = text[inserted["line_start"]:inserted["line_end"]]
                            line += "\r\n" if inserted_line.endswith("\r\n") else "\n" if inserted_line.endswith("\n") else ""
                        text = text[:inserted["line_start"]] + line + text[inserted["line_end"]:]
                else:
                    inserted = _assignment(applied_text, "Graphics", item["key"])
                    _require(inserted is not None and text[found["line_start"]:found["line_end"]] ==
                             applied_text[inserted["line_start"]:inserted["line_end"]],
                             "UNDO_CONFLICT", "An inserted performance line was edited externally")
                    text = _remove(text, item["key"])
            restored = before if current == applied else _configuration_bytes(text)
            if any(item["option_id"] == "auto_frameskip" for item in diff):
                restored_text, global_text = _configuration_text(restored), _configuration_text(_read(control["_config"]))
                _require(not (self._effective(restored_text, global_text, "AutoFrameSkip", True) is True and
                              self._effective(restored_text, global_text, "SkipBufferEffects", True) is True),
                         "UNDO_CONFLICT", "Undo would enable automatic frameskip with current Skip Buffer Effects. Review the newer native settings first.")
            tx = "performance-undo-" + uuid.uuid4().hex
            result = {"transaction_id": tx, "undone_transaction_id": original, "game_id": metadata["game_id"],
                      "generation": generation + 1, "applied": True, "idempotent": False,
                      "scope": "per-game", "candidate_status": "untested", "runtime_observed": False,
                      "emulator_binary_changed": False}
            transactions.commit(tx, request_id, "undo", original,
                                [(path, current, restored), (self.meta, _read(self.meta), _encoded({"schema": 1, "generation": generation + 1}))],
                                metadata, result)
            return result

    def recover(self):
        with self.experience._window():
            self._recover()
