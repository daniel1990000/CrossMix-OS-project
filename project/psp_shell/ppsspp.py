# SPDX-License-Identifier: MIT
"""Supported PPSSPP theme adoption with exact-profile and stopped-writer gates.

This is original adapter code, not copied PPSSPP implementation. The emulator
continues to own all UI, rendering, input, save-state and keyboard behavior.
"""
from __future__ import annotations

import configparser
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
import uuid

from .controls import (
    _ppsspp_assignment as _assignment, _configuration_bytes, _configuration_text, _file_digest,
    _process_running, _ppsspp_semantic_token as _semantic_token, _under,
    set_ppsspp_config_token as set_config_token,
)
from .settings import (
    SettingsError, _Transactions, _atomic_write, _check_generation, _directory,
    _encoded, _fields, _generation, _identifier, _json, _json_bytes, _locked,
    _read, _require, _schema, _sha,
)


UPSTREAM_COMMIT = "d357e6a32934800d3d80b49f910a603e1b069751"
UPSTREAM_VERSION = "v1.20.3"
THEME_SCHEMA_SHA256 = "c2c3910f9bcda69c073dcd6bb4a3ca5b84438632e87ff5aebcea1a0d5d07ffcd"
THEME_NAMES = ("Spruce Midnight", "Spruce Midnight High Contrast")
COLOR_KEYS = frozenset((
    "ItemStyleFg", "ItemStyleBg", "ItemFocusedStyleFg", "ItemFocusedStyleBg",
    "ItemDownStyleFg", "ItemDownStyleBg", "ItemDisabledStyleFg", "ItemDisabledStyleBg",
    "HeaderStyleFg", "HeaderStyleBg", "InfoStyleFg", "InfoStyleBg", "PopupStyleFg",
    "PopupStyleBg", "PopupTitleStyleFg", "PopupTitleStyleBg", "TooltipStyleFg",
    "TooltipStyleBg", "CollapsibleHeaderStyleFg", "CollapsibleHeaderStyleBg",
    "BackgroundColor", "ScrollbarColor", "PopupSliderColor", "PopupSliderFocusedColor",
))
PLATFORM_CONFIG = "Saves/.config/ppsspp/PSP/SYSTEM/ppsspp-SmartPro.ini"
THEME_DIRECTORY = "Saves/.config/ppsspp/PSP/themes"
THEME_FILENAME = "spruce-midnight.ini"


class PPSSPPError(SettingsError):
    pass


def validate_theme(data: bytes) -> dict:
    """Validate only the supported, pinned palette schema; no script/assets API."""
    _require(isinstance(data, bytes) and 0 < len(data) <= 65536 and b"\0" not in data,
             "INVALID_THEME", "Theme must be bounded UTF-8 INI data")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        parser.read_string(data.decode("utf-8"))
        _require(not parser.defaults() and set(parser.sections()) == set(THEME_NAMES),
                 "INVALID_THEME", "Theme contains an unknown section or default")
        output = {}
        for name in THEME_NAMES:
            section = parser[name]
            _require(set(section) == COLOR_KEYS | {"Name"}, "INVALID_THEME", "Theme contains unsupported/missing keys")
            _require(json.loads(section["Name"]) == name, "INVALID_THEME", "Theme name mismatch")
            colors = {}
            for key in COLOR_KEYS:
                token = json.loads(section[key])
                _require(isinstance(token, str) and bool(re.fullmatch(r"#[a-fA-F0-9]{8}", token)),
                         "INVALID_THEME", "Colors must use PPSSPP's quoted #RRGGBBAA format")
                colors[key] = token.upper()
            output[name] = colors
        return {"names": list(THEME_NAMES), "colors": output, "sha256": hashlib.sha256(data).hexdigest(),
                "schema_source_commit": UPSTREAM_COMMIT, "theme_cpp_sha256": THEME_SCHEMA_SHA256,
                "custom_fonts_or_icons": False}
    except (configparser.Error, ValueError, UnicodeError, TypeError) as error:
        if isinstance(error, SettingsError):
            raise
        raise PPSSPPError("INVALID_THEME", "Theme is not supported bounded INI data") from error


def palette_contrast(foreground: str, background: str) -> float:
    """WCAG contrast of opaque palette endpoints, independent of rendering claims."""
    def luminance(value: str):
        channels = [int(value[n:n + 2], 16) / 255 for n in (1, 3, 5)]
        linear = [part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4 for part in channels]
        return sum(part * weight for part, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class PPSSPPThemeManager:
    """Preview/install/undo a custom palette without replacing PPSSPP assets.

    The caller supplies a trusted compatibility profile and a serialized,
    quiescent write window. The shipped example profile is deliberately
    unqualified because source validation does not identify the installed binary.
    """

    def __init__(self, sd_root, state_dir, profile, *, quiescent: Callable,
                 process_probe: Callable | None = None, theme_file=None, fault_hook=None):
        self.sd_root = Path(sd_root).resolve(strict=True)
        _require(self.sd_root.is_dir() and callable(quiescent), "INVALID_ARGUMENT", "Invalid installed root or write gate")
        self.state_dir = _directory(Path(state_dir))
        self.previews = _directory(self.state_dir / "previews")
        self.meta = self.state_dir / "generation.json"
        self.lock = self.state_dir / "ppsspp-theme.lock"
        self.profile_source = Path(profile) if isinstance(profile, (str, Path)) else copy.deepcopy(profile)
        self.theme_file = Path(theme_file) if theme_file else Path(__file__).resolve().parents[1] / "ppsspp/theme" / THEME_FILENAME
        self.quiescent, self.process_probe = quiescent, process_probe or _process_running
        self.fault_hook = fault_hook
        self._profile()
        validate_theme(_read(self.theme_file))
        with _locked(self.lock):
            self._transactions().recover()
            if _read(self.meta, optional=True) is None:
                _atomic_write(self.meta, _encoded({"schema": 1, "generation": 0}))

    def _profile(self, writable=False) -> dict:
        raw = _read(self.profile_source) if isinstance(self.profile_source, Path) else _encoded(self.profile_source)
        value = _json_bytes(raw)
        _schema(value)
        _identifier(value.get("id"), "profile ID")
        _require(value.get("device") == "TRIMUI_SMART_PRO" and value.get("engine") == "ppsspp",
                 "UNSUPPORTED_PROFILE", "Profile does not target original Smart Pro PPSSPP")
        _require(value.get("source_commit") == UPSTREAM_COMMIT and value.get("source_version") == UPSTREAM_VERSION and
                 value.get("theme_schema_sha256") == THEME_SCHEMA_SHA256,
                 "UNSUPPORTED_PROFILE", "Theme source/version contract is not supported")
        _require(value.get("config") == PLATFORM_CONFIG and value.get("theme_directory") == THEME_DIRECTORY,
                 "UNSUPPORTED_PROFILE", "PPSSPP authoritative config or memstick path has not been mapped")
        executable = value.get("executable")
        _require(isinstance(executable, str) and Path(executable).parent == Path("Emu/PSP"),
                 "UNSUPPORTED_PROFILE", "PPSSPP executable is outside the approved directory")
        value = {**value, "_profile_hash": _sha(raw),
                 "_config": _under(self.sd_root, PLATFORM_CONFIG),
                 "_theme": _under(self.sd_root, THEME_DIRECTORY + "/" + THEME_FILENAME, exists=False)}
        _read(value["_config"])
        if writable:
            _require(value.get("qualified") is True and value.get("writer_inventory_verified") is True and
                     value.get("path_contract_verified") is True and value.get("installed_version") == UPSTREAM_VERSION,
                     "UNSUPPORTED_PROFILE", "Installed PPSSPP build and write paths have not been qualified")
            digest = value.get("executable_sha256")
            binary = _under(self.sd_root, executable)
            _require(isinstance(digest, str) and bool(re.fullmatch(r"[a-f0-9]{64}", digest)) and _file_digest(binary) == digest,
                     "UNSUPPORTED_PROFILE", "Installed PPSSPP fingerprint changed")
            _require(self.quiescent() is True, "BUSY_WRITER", "Theme adoption requires a quiescent session")
            writers = value.get("writer_executables")
            _require(isinstance(writers, list) and 0 < len(writers) <= 16,
                     "UNSUPPORTED_PROFILE", "Missing PPSSPP configuration-writer inventory")
            for writer in {binary, *(_under(self.sd_root, item) for item in writers)}:
                _require(self.process_probe(writer) is False, "BUSY_GAME", "PPSSPP or another config writer is running")
        return value

    def _state(self) -> dict:
        value = _json(self.meta)
        _schema(value)
        _generation(value.get("generation"))
        return value

    @staticmethod
    def _validate_preview(record: dict) -> None:
        _require(record.get("theme") in THEME_NAMES and type(record.get("motion")) is bool,
                 "INVALID_PREVIEW", "Unknown theme or motion in preview")
        expected = [("Theme", "ThemeName", record["theme"]),
                    ("General", "BackgroundAnimation", "3" if record["motion"] else "0")]
        diff = record.get("diff")
        _require(isinstance(diff, list) and len(diff) == 2, "INVALID_PREVIEW", "Unexpected theme diff")
        for item, (section, key, after) in zip(diff, expected):
            _require(isinstance(item, dict) and item.get("section") == section and item.get("key") == key and
                     item.get("after") == after and type(item.get("before_present")) is bool,
                     "INVALID_PREVIEW", "Theme preview contains an unowned setting")

    def _validate_journal(self, journal: dict) -> None:
        profile = self._profile()
        _require(journal.get("metadata", {}).get("profile_id") == profile["id"],
                 "INVALID_TRANSACTION", "Theme transaction belongs to another profile")
        paths = [item["path"] for item in journal["files"]]
        expected = [str(profile["_theme"]), str(profile["_config"]), str(self.meta)]
        _require(paths == expected or (journal.get("operation") == "undo" and paths == expected[1:]),
                 "UNSAFE_PATH", "Theme transaction targets an unowned file")

    def _transactions(self) -> _Transactions:
        return _Transactions(self.state_dir / "transactions", self._validate_journal,
                             self.fault_hook,
                             lambda journal, persist: self._profile(writable=True),
                             lambda journal: self._profile(writable=True))

    def status(self) -> dict:
        profile = self._profile()
        data = _configuration_text(_read(profile["_config"]))
        selection = _assignment(data, "Theme", "ThemeName")
        animation = _assignment(data, "General", "BackgroundAnimation")
        animation = _semantic_token(animation["token"]) if animation else "1"
        available, gate = True, ""
        try:
            self._profile(writable=True)
        except SettingsError as error:
            available, gate = False, error.code
        return {"profile_id": profile["id"], "generation": self._state()["generation"],
                "theme": _semantic_token(selection["token"]) if selection else "Default",
                "motion": {"0": False, "1": True, "2": True, "3": True}.get(animation),
                "available_themes": list(THEME_NAMES), "adoption_available": available,
                "gate_reason": gate, "emulator_binary_changed": False}

    def preview(self, params: dict) -> dict:
        _fields(params, {"theme", "motion", "expected_generation"}, {"theme", "motion", "expected_generation"})
        _require(params["theme"] in THEME_NAMES and type(params["motion"]) is bool,
                 "INVALID_ARGUMENT", "Unknown theme or motion preference")
        with _locked(self.lock):
            self._transactions().recover()
            state = self._state()
            generation = _check_generation(params, state)
            profile = self._profile()
            source = _read(self.theme_file)
            manifest = validate_theme(source)
            before_theme = _read(profile["_theme"], optional=True)
            config = _read(profile["_config"])
            text = _configuration_text(config)
            diff = []
            for section, key, after in (("Theme", "ThemeName", params["theme"]),
                                        ("General", "BackgroundAnimation", "3" if params["motion"] else "0")):
                found = _assignment(text, section, key)
                diff.append({"section": section, "key": key, "before_present": found is not None,
                             "before_token": found["token"] if found else None,
                             "before": _semantic_token(found["token"]) if found else None, "after": after})
                text = set_config_token(text, key, json.dumps(after) if section == "Theme" else after, section=section)
            preview_id = "theme-preview-" + uuid.uuid4().hex
            record = {"schema": 1, "preview_id": preview_id, "profile_id": profile["id"],
                      "profile_hash": profile["_profile_hash"], "generation": generation,
                      "theme_sha256": manifest["sha256"], "before_theme_present": before_theme is not None,
                      "before_theme_sha256": _sha(before_theme or b""), "config_sha256": _sha(config),
                      "after_config_sha256": _sha(_configuration_bytes(text)), "diff": diff,
                      "theme": params["theme"], "motion": params["motion"]}
            _atomic_write(self.previews / (preview_id + ".json"), _encoded(record))
            capabilities = self.status()
            return {"preview_id": preview_id, "generation": generation, "profile_id": profile["id"],
                    "diff": diff, "theme_sha256": manifest["sha256"],
                    "overwrites_existing_theme": before_theme is not None and before_theme != source,
                    "adoption_available": capabilities["adoption_available"], "gate_reason": capabilities["gate_reason"],
                    "gameplay_changed": False, "emulator_binary_changed": False}

    def apply(self, params: dict) -> dict:
        _fields(params, {"preview_id", "expected_generation", "request_id", "confirm_overwrite"},
                {"preview_id", "expected_generation", "request_id"})
        preview_id = _identifier(params["preview_id"], "preview ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        _require(type(params.get("confirm_overwrite", False)) is bool, "INVALID_ARGUMENT", "Overwrite confirmation must be boolean")
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "apply", preview_id)
            if replay:
                return replay
            profile = self._profile(writable=True)
            state = self._state()
            generation = _check_generation(params, state)
            record = _json(self.previews / (preview_id + ".json"))
            _schema(record)
            self._validate_preview(record)
            source = _read(self.theme_file)
            validate_theme(source)
            before_theme = _read(profile["_theme"], optional=True)
            before_config = _read(profile["_config"])
            _require(record.get("preview_id") == preview_id and record.get("profile_id") == profile["id"] and
                     record.get("profile_hash") == profile["_profile_hash"] and record.get("generation") == generation and
                     record.get("theme_sha256") == _sha(source) and record.get("config_sha256") == _sha(before_config) and
                     record.get("before_theme_present") == (before_theme is not None) and
                     record.get("before_theme_sha256") == _sha(before_theme or b""),
                     "STALE_SNAPSHOT", "Theme, emulator profile, or configuration changed since preview")
            _require(before_theme is None or before_theme == source or params.get("confirm_overwrite") is True,
                     "OVERWRITE_CONFIRMATION_REQUIRED", "An existing custom theme file needs explicit overwrite confirmation")
            text = _configuration_text(before_config)
            for change in record["diff"]:
                token = json.dumps(change["after"]) if change["section"] == "Theme" else change["after"]
                text = set_config_token(text, change["key"], token, section=change["section"])
            after_config = _configuration_bytes(text)
            _require(_sha(after_config) == record["after_config_sha256"], "INVALID_PREVIEW", "Theme preview checksum mismatch")
            _directory(profile["_theme"].parent)
            transaction_id = "theme-tx-" + uuid.uuid4().hex
            result = {"transaction_id": transaction_id, "generation": generation + 1,
                      "profile_id": profile["id"], "theme": record["theme"], "applied": True,
                      "idempotent": False, "gameplay_changed": False, "emulator_binary_changed": False}
            transactions.commit(transaction_id, request_id, "apply", preview_id,
                                [(profile["_theme"], before_theme, source), (profile["_config"], before_config, after_config),
                                 (self.meta, _read(self.meta), _encoded({**state, "generation": generation + 1}))],
                                {"profile_id": profile["id"], "diff": record["diff"], "theme_sha256": _sha(source)}, result)
            return result

    def undo(self, params: dict) -> dict:
        _fields(params, {"transaction_id", "expected_generation", "request_id"},
                {"transaction_id", "expected_generation", "request_id"})
        original_id = _identifier(params["transaction_id"], "transaction ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "undo", original_id)
            if replay:
                return replay
            journal = transactions.journal(original_id)
            _require(journal.get("operation") == "apply" and journal["status"] == "committed",
                     "INVALID_TRANSACTION", "Only a committed theme adoption can be undone")
            profile = self._profile(writable=True)
            state = self._state()
            generation = _check_generation(params, state)
            config = _read(profile["_config"])
            text = _configuration_text(config)
            applied_text = _configuration_text(transactions.snapshot(journal, 1, True))
            for change in journal["metadata"]["diff"]:
                section, key = change["section"], change["key"]
                _require((section, key) in (("Theme", "ThemeName"), ("General", "BackgroundAnimation")),
                         "INVALID_TRANSACTION", "Theme journal contains an unowned setting")
                found = _assignment(text, section, key)
                _require(found is not None and _semantic_token(found["token"]) == change["after"],
                         "UNDO_CONFLICT", "A theme setting was changed outside this transaction")
                if change["before_present"]:
                    text = set_config_token(text, key, change["before_token"], section=section)
                else:
                    inserted = _assignment(applied_text, section, key)
                    _require(inserted is not None and text[found["line_start"]:found["line_end"]] ==
                             applied_text[inserted["line_start"]:inserted["line_end"]],
                             "UNDO_CONFLICT", "An inserted theme-setting line changed externally")
                    text = text[:found["line_start"]] + text[found["line_end"]:]
            changes = [(profile["_config"], config, _configuration_bytes(text)),
                       (self.meta, _read(self.meta), _encoded({**state, "generation": generation + 1}))]
            retained = not journal["files"][0]["before_exists"]
            if not retained:
                current_theme = _read(profile["_theme"])
                _require(_sha(current_theme) == journal["files"][0]["after_sha256"],
                         "UNDO_CONFLICT", "The theme palette was edited outside this transaction")
                changes.insert(0, (profile["_theme"], current_theme, transactions.snapshot(journal, 0)))
            transaction_id = "theme-undo-" + uuid.uuid4().hex
            result = {"transaction_id": transaction_id, "undone_transaction_id": original_id,
                      "generation": generation + 1, "applied": True, "idempotent": False,
                      "theme_file_retained_unselected": retained, "gameplay_changed": False,
                      "emulator_binary_changed": False}
            transactions.commit(transaction_id, request_id, "undo", original_id, changes,
                                {"profile_id": profile["id"], "undone_transaction_id": original_id}, result)
            return result

    def recover(self) -> None:
        with _locked(self.lock):
            self._transactions().recover()
