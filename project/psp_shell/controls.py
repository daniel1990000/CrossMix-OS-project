"""Original control-policy and stopped-emulator configuration adapters.

The UI convention, spruce IGM, RetroArch menu and gameplay are distinct
surfaces.  No shipped profile below claims a hardware-qualified emulator write.
"""

from __future__ import annotations

import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable
import uuid

from .settings import (
    MAX_FILE, SettingsError, _Transactions, _atomic_write, _check_generation,
    _directory, _encoded, _fields, _generation, _identifier, _json, _json_bytes,
    _locked, _read, _require, _schema, _sha,
)


SMARTPRO_BUTTON_LABELS = {"south": "B", "east": "A", "north": "X", "west": "Y"}


def ui_convention(confirm: str) -> dict:
    """Return frontend actions/hints without changing gameplay mappings."""
    _require(isinstance(confirm, str) and confirm in {"south", "east"}, "INVALID_ARGUMENT", "Confirm must be south or east")
    back = "east" if confirm == "south" else "south"
    return {"schema": 1, "confirm": confirm, "back": back,
            "physical_to_action": {confirm: "confirm", back: "back",
                                   "north": "options", "west": "alternate"},
            "hints": {"confirm": SMARTPRO_BUTTON_LABELS[confirm],
                      "back": SMARTPRO_BUTTON_LABELS[back]},
            "gameplay_changed": False}


def validate_ui_mapping(mapping: dict) -> dict:
    _require(isinstance(mapping, dict) and set(mapping) == set(SMARTPRO_BUTTON_LABELS),
             "INVALID_MAPPING", "All four physical face buttons need a UI action")
    required = {"confirm", "back", "options", "alternate"}
    _require(all(isinstance(item, str) for item in mapping.values()) and set(mapping.values()) == required,
             "INVALID_MAPPING", "UI actions must remain reachable exactly once")
    return copy.deepcopy(mapping)


def _configuration_text(data: bytes) -> str:
    _require(len(data) <= MAX_FILE and b"\0" not in data, "INVALID_CONFIG", "Invalid configuration bytes")
    return data.decode("utf-8", "surrogateescape")


def _configuration_bytes(text: str) -> bytes:
    data = text.encode("utf-8", "surrogateescape")
    _require(len(data) <= MAX_FILE, "TOO_LARGE", "Configuration exceeds its byte budget")
    return data


def _ppsspp_name(value: str) -> str:
    # The pinned parser compares ASCII INI names; Unicode case folding could
    # incorrectly equate another byte sequence with an owned ASCII key.
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _configuration_lines(text: str, ppsspp_ini: bool) -> list[str]:
    if not ppsspp_ini:
        return text.splitlines(keepends=True)
    # std::getline uses LF only; Python splitlines also treats Unicode and
    # control characters as boundaries, which would invent engine settings.
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _visible_line(line: str, position: int, ppsspp_ini: bool) -> tuple[str, str, int]:
    content = line.rstrip("\r\n")
    if ppsspp_ini:
        stripped = content.lstrip(" \t\r\n")
        offset = len(content) - len(stripped)
        if stripped.startswith("\ufeff"):
            stripped, offset = stripped[1:], offset + 1
    else:
        parse_offset = 1 if position == 0 and content.startswith("\ufeff") else 0
        stripped = content[parse_offset:].lstrip(" \t")
        offset = parse_offset + len(content[parse_offset:]) - len(stripped)
    return content, stripped, offset


def _assignment(text: str, section: str, key: str, *, ppsspp_ini: bool = False) -> dict | None:
    _require(len(_configuration_bytes(text)) <= MAX_FILE and "\0" not in text,
             "INVALID_CONFIG", "Invalid configuration text")
    active = ""
    owned_sections = 0
    wanted_section = _ppsspp_name(section) if ppsspp_ini else section
    wanted_key = _ppsspp_name(key) if ppsspp_ini else key
    result = None
    position = 0
    for line in _configuration_lines(text, ppsspp_ini):
        content, stripped, offset = _visible_line(line, position, ppsspp_ini)
        if stripped.startswith("["):
            closing = stripped.find("]")
            _require(closing > 0, "INVALID_CONFIG", "Malformed configuration section")
            # Pinned PPSSPP IniFile compares names without regard to case,
            # and retains spaces inside section brackets.
            active = stripped[1:closing]
            active = _ppsspp_name(active) if ppsspp_ini else active.strip()
            if ppsspp_ini and active == wanted_section:
                owned_sections += 1
                _require(owned_sections == 1, "AMBIGUOUS_CONFIG", "Duplicate owned configuration section")
        elif active == wanted_section and stripped and not stripped.startswith(("#", ";")) and "=" in stripped:
            equals = content.find("=", offset)
            actual_key = content[offset:equals].strip(" \t\r\n") if ppsspp_ini else content[offset:equals].strip()
            if (_ppsspp_name(actual_key) if ppsspp_ini else actual_key) == wanted_key:
                _require(result is None, "AMBIGUOUS_CONFIG", "Duplicate owned configuration key")
                start = equals + 1
                while start < len(content) and content[start] in " \t":
                    start += 1
                end = len(content)
                if ppsspp_ini:
                    # IniFile::ParseLineValue strips double quotes only when
                    # they surround the complete value, otherwise # starts a
                    # comment unless immediately escaped. Semicolons are data.
                    value = content[start:].strip(" \t\r\n")
                    if not (len(value) >= 2 and value.startswith('"') and value.endswith('"')):
                        for index in range(start, len(content)):
                            if content[index] == "#" and (index == start or content[index - 1] != "\\"):
                                end = index
                                break
                else:
                    quote = None
                    escaped = False
                    for index in range(start, len(content)):
                        character = content[index]
                        if escaped:
                            escaped = False
                        elif quote and character == "\\":
                            escaped = True
                        elif character in {"\"", "'"} and (quote is None or quote == character):
                            quote = None if quote else character
                        elif quote is None and character in {"#", ";"}:
                            end = index
                            break
                    _require(quote is None, "INVALID_CONFIG", "Unterminated owned configuration value")
                while end > start and content[end - 1] in " \t":
                    end -= 1
                result = {"line_start": position, "line_end": position + len(line),
                          "value_start": position + start, "value_end": position + end,
                          "token": content[start:end]}
        position += len(line)
    return result


def _valid_assignment(section: str, key: str, raw_token: str) -> None:
    _require(isinstance(section, str) and not any(c in section for c in "[]\r\n\0") and
             isinstance(key, str) and bool(re.fullmatch(r"[A-Za-z0-9_. -]{1,128}", key)) and
             isinstance(raw_token, str) and not any(c in raw_token for c in "\r\n\0"),
             "INVALID_ARGUMENT", "Invalid configuration assignment")


def set_config_token(text: str, key: str, raw_token: str, *, section: str = "", ppsspp_ini: bool = False) -> str:
    """Change exactly one unique value token; retain comments/unknown bytes."""
    _valid_assignment(section, key, raw_token)
    found = _assignment(text, section, key, ppsspp_ini=ppsspp_ini)
    if found:
        return text[:found["value_start"]] + raw_token + text[found["value_end"]:]
    newline = "\r\n" if "\r\n" in text else "\n"
    addition = f"{key} = {raw_token}{newline}"
    position = 0
    active = ""
    wanted_section = _ppsspp_name(section) if ppsspp_ini else section
    seen_section = not section
    insert_at = len(text)
    for line in _configuration_lines(text, ppsspp_ini):
        _, stripped, _ = _visible_line(line, position, ppsspp_ini)
        if stripped.startswith("["):
            closing = stripped.find("]")
            _require(closing > 0, "INVALID_CONFIG", "Malformed configuration section")
            if active == wanted_section and seen_section:
                insert_at = position
                break
            active = stripped[1:closing]
            active = _ppsspp_name(active) if ppsspp_ini else active.strip()
            seen_section |= active == wanted_section
        position += len(line)
    if not seen_section:
        prefix = "" if not text or text.endswith(("\n", "\r")) else newline
        return text + prefix + f"[{section}]{newline}" + addition
    prefix = "" if insert_at == 0 or text[insert_at - 1] in "\n\r" else newline
    return text[:insert_at] + prefix + addition + text[insert_at:]


def _semantic_token(token: str, *, ppsspp_ini: bool = False, boolean: bool = False):
    stripped = token.strip(" \t\r\n") if ppsspp_ini else token.strip()
    if ppsspp_ini:
        # PPSSPP strips surrounding quotes; it does not JSON-decode INI values.
        if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
            stripped = stripped[1:-1]
        else:
            stripped = stripped.replace("\\#", "#")
        if boolean and _ppsspp_name(stripped) in {"true", "false", "1", "0"}:
            return _ppsspp_name(stripped) in {"true", "1"}
        return stripped
    if stripped.startswith('"'):
        try:
            stripped = json.loads(stripped)
        except ValueError as error:
            raise SettingsError("INVALID_CONFIG", "Malformed quoted owned value") from error
        _require(isinstance(stripped, str), "INVALID_CONFIG", "Owned value is not a string")
    if stripped in {"true", "false"}:
        return stripped == "true"
    return stripped


def _ppsspp_assignment(text: str, section: str, key: str) -> dict | None:
    """Find a unique owned token using the pinned PPSSPP INI conventions."""
    return _assignment(text, section, key, ppsspp_ini=True)


def set_ppsspp_config_token(text: str, key: str, raw_token: str, *, section: str = "") -> str:
    """Retain PPSSPP spelling/comments while changing a unique owned token."""
    return set_config_token(text, key, raw_token, section=section, ppsspp_ini=True)


def _ppsspp_semantic_token(token: str, *, boolean: bool = False):
    return _semantic_token(token, ppsspp_ini=True, boolean=boolean)


def _encoded_token(value) -> str:
    if type(value) is bool:
        return '"true"' if value else '"false"'
    _require(isinstance(value, str) and len(value) <= 128 and not any(c in value for c in "\r\n\0"),
             "UNSUPPORTED_PROFILE", "Invalid menu extension value")
    return json.dumps(value, ensure_ascii=False)


def _under(root: Path, relative: str, *, exists: bool = True) -> Path:
    _require(isinstance(relative, str) and relative and "\0" not in relative,
             "UNSAFE_PATH", "Invalid profile path")
    path = Path(relative)
    _require(not path.is_absolute() and ".." not in path.parts, "UNSAFE_PATH", "Profile path escapes the installed root")
    full = root / path
    current = root
    for part in path.parts:
        current /= part
        _require(not current.is_symlink(), "UNSAFE_PATH", "Profile paths cannot traverse symlinks")
    try:
        result = full.resolve(strict=exists)
        result.relative_to(root)
    except (ValueError, OSError) as error:
        raise SettingsError("UNSAFE_PATH", "Profile path is missing or outside the installed root") from error
    return result


def _file_digest(path: Path, limit: int = 268_435_456) -> str:
    try:
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
                 "UNSUPPORTED_PROFILE", "Invalid emulator executable")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "rb") as stream:
            while True:
                data = stream.read(65_536)
                if not data:
                    break
                size += len(data)
                _require(size <= limit, "TOO_LARGE", "Executable exceeds its fingerprint budget")
                digest.update(data)
        return digest.hexdigest()
    except OSError as error:
        raise SettingsError("UNSUPPORTED_PROFILE", "Cannot fingerprint the installed emulator") from error


def _process_running(executable: Path) -> bool:
    try:
        expected = executable.stat()
        inaccessible = False
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                actual = (entry / "exe").stat()
                if (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino):
                    return True
            except OSError as error:
                if error.errno not in {errno.ENOENT, errno.ESRCH}:
                    inaccessible = True
        _require(not inaccessible, "PROCESS_STATE_UNKNOWN", "Some process identities cannot be inspected")
        return False
    except OSError as error:
        raise SettingsError("PROCESS_STATE_UNKNOWN", "Cannot establish stopped-emulator state") from error


class EmulatorConfigAdapter:
    """Writes only a trusted, fingerprint-pinned menu surface while quiescent."""

    def __init__(self, sd_root, state_dir, profiles_dir, *, quiescent: Callable,
                 process_probe: Callable | None = None, fault_hook=None):
        # The installed SD/profile roots must already exist. Constructing this
        # adapter is never allowed to seed an installed card or config tree.
        self.sd_root = Path(sd_root).resolve(strict=True)
        self.profiles_dir = Path(profiles_dir).resolve(strict=True)
        _require(self.sd_root.is_dir() and self.profiles_dir.is_dir(), "UNSAFE_PATH", "Missing installed profile root")
        self.state_dir = _directory(Path(state_dir))
        self.meta = self.state_dir / "generation.json"
        self.lock = self.state_dir / "emulator-settings.lock"
        self.previews = _directory(self.state_dir / "previews")
        self.quiescent = quiescent
        self.process_probe = process_probe or _process_running
        self.fault_hook = fault_hook
        with _locked(self.lock):
            self._transactions().recover()
            if _read(self.meta, optional=True) is None:
                _atomic_write(self.meta, _encoded({"schema": 1, "generation": 0}))

    def _state(self) -> dict:
        value = _json(self.meta)
        _schema(value)
        _generation(value.get("generation"))
        return value

    def _profile(self, profile_id: str, *, writable: bool = False) -> dict:
        _require(isinstance(profile_id, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", profile_id)),
                 "INVALID_ARGUMENT", "Invalid emulator profile ID")
        path = _under(self.profiles_dir, profile_id + ".json")
        raw = _read(path)
        value = _json_bytes(raw)
        _schema(value)
        _require(value.get("id") == profile_id and value.get("device") == "TRIMUI_SMART_PRO",
                 "UNSUPPORTED_PROFILE", "Profile does not identify the original Smart Pro")
        value = {**value, "_profile_hash": _sha(raw)}
        if writable:
            _require(value.get("qualified") is True, "UNSUPPORTED_PROFILE", "Emulator profile has not been qualified")
            _require(value.get("writer_inventory_verified") is True,
                     "UNSUPPORTED_PROFILE", "Configuration-writer inventory has not been verified")
            executable = _under(self.sd_root, value.get("executable"))
            digest = value.get("executable_sha256")
            _require(isinstance(digest, str) and bool(re.fullmatch(r"[a-f0-9]{64}", digest)) and
                     _file_digest(executable) == digest,
                     "UNSUPPORTED_PROFILE", "Installed emulator fingerprint does not match the qualified profile")
            _require(self.quiescent() is True, "BUSY_WRITER", "A quiescent emulator-write window is required")
            writers = value.get("writer_executables")
            _require(isinstance(writers, list) and 0 < len(writers) <= 16,
                     "UNSUPPORTED_PROFILE", "Missing configuration-writer inventory")
            for writer in {executable, *(_under(self.sd_root, item) for item in writers)}:
                _require(self.process_probe(writer) is False, "BUSY_GAME", "An emulator or configuration writer is running")
        value["_config"] = _under(self.sd_root, value.get("config"))
        _read(value["_config"])
        return value

    @staticmethod
    def _mapping(profile: dict, confirm: str) -> tuple[str, dict]:
        _require(isinstance(confirm, str) and confirm in {"south", "east"}, "INVALID_ARGUMENT", "Confirm must be south or east")
        surface = profile.get("surface")
        if profile.get("engine") == "retroarch" and surface == "standard_menu":
            _require(isinstance(profile.get("supported_keys"), list) and
                     "menu_swap_ok_cancel_buttons" in profile["supported_keys"],
                     "UNSUPPORTED_CAPABILITY", "RetroArch menu swap is not declared by this profile")
            values = profile.get("confirm_values", {})
            _require(isinstance(values, dict) and set(values) == {"south", "east"} and all(type(item) is bool for item in values.values()) and
                     values["south"] != values["east"],
                     "UNSUPPORTED_PROFILE", "Physical-to-RetroArch menu mapping is unverified")
            return "", {"menu_swap_ok_cancel_buttons": values[confirm]}
        if surface == "spruce_igm":
            raise SettingsError("UNSUPPORTED_CAPABILITY", "spruce IGM controls are separate from the standard RetroArch menu and need their own qualified adapter")
        if profile.get("engine") == "ppsspp":
            extension = profile.get("native_menu_extension", {})
            _require(surface == "native_menu" and isinstance(extension, dict) and extension.get("qualified") is True and
                     isinstance(extension.get("source_commit"), str) and
                     bool(re.fullmatch(r"[a-f0-9]{40}", extension["source_commit"])),
                     "UNSUPPORTED_CAPABILITY", "Independent PPSSPP menu controls are not qualified; gameplay and PSP button preference stay unchanged")
            # These are project extension keys, never claims about stock PPSSPP.
            conventions = extension.get("conventions")
            _require(extension.get("section") == "ProjectNativeMenu" and isinstance(conventions, dict) and
                     set(conventions) == {"south", "east"},
                     "UNSUPPORTED_PROFILE", "Unknown independent-menu extension schema")
            for position, values in conventions.items():
                _require(isinstance(values, dict) and
                         set(values) == {"IndependentMenuControls", "NativeMenuConfirm", "NativeMenuBack"} and
                         values["IndependentMenuControls"] is True and values["NativeMenuConfirm"] == position and
                         values["NativeMenuBack"] == ("east" if position == "south" else "south"),
                         "UNSUPPORTED_PROFILE", "Independent-menu conventions must enable the exact physical Confirm/Back pair")
            _require(Path(profile["config"]).name.startswith("ppsspp"),
                     "UNSUPPORTED_PROFILE", "Menu extension cannot edit PSP gameplay controls")
            return "ProjectNativeMenu", {"IndependentMenuControls": True,
                                         "NativeMenuConfirm": confirm,
                                         "NativeMenuBack": "east" if confirm == "south" else "south"}
        raise SettingsError("UNSUPPORTED_CAPABILITY", "No qualified menu-control adapter exists for this surface")

    @staticmethod
    def _menu_change(profile: dict, text: str, section: str, values: dict) -> tuple[str, list]:
        """Recompute the complete owned diff before approving any write."""
        ppsspp_ini = profile.get("engine") == "ppsspp"
        diff = []
        for key, value in values.items():
            found = _assignment(text, section, key, ppsspp_ini=ppsspp_ini)
            previous = _semantic_token(found["token"], ppsspp_ini=ppsspp_ini,
                                       boolean=key == "IndependentMenuControls") if found else None
            if previous == value:
                continue
            diff.append({"key": key, "section": section, "before_present": found is not None,
                         "before_token": found["token"] if found else None,
                         "before": previous, "after": value})
            text = set_config_token(text, key, _encoded_token(value), section=section, ppsspp_ini=ppsspp_ini)
        return text, diff

    def _configured_controls(self, profile: dict, text: str, *, qualified: bool = False) -> dict:
        """Describe persisted configuration, never an observed running engine."""
        ppsspp_ini = profile.get("engine") == "ppsspp"
        section, values = self._mapping(profile, "south")
        observed = {}
        for key in values:
            found = _assignment(text, section, key, ppsspp_ini=ppsspp_ini)
            observed[key] = _semantic_token(found["token"], ppsspp_ini=ppsspp_ini,
                                             boolean=key == "IndependentMenuControls") if found else None
        configured_confirm = None
        for confirm in ("south", "east"):
            if observed == self._mapping(profile, confirm)[1]:
                configured_confirm = confirm
                break
        return {"configured_confirm": configured_confirm,
                "independent_menu_controls_enabled": observed.get("IndependentMenuControls") is True if ppsspp_ini else None,
                "configuration_effective": qualified and configured_confirm is not None}

    def _validate_journal(self, journal: dict) -> None:
        profile = self._profile(journal.get("metadata", {}).get("profile_id"))
        _require([item["path"] for item in journal["files"]] == [str(profile["_config"]), str(self.meta)],
                 "UNSAFE_PATH", "Emulator journal targets an unowned file")

    def _before_recovery(self, journal: dict, _persist: Callable) -> None:
        self._profile(journal["metadata"]["profile_id"], writable=True)

    def _transactions(self) -> _Transactions:
        return _Transactions(self.state_dir / "transactions", self._validate_journal,
                             self.fault_hook, self._before_recovery,
                             lambda journal: self._profile(journal["metadata"]["profile_id"], writable=True))

    def snapshot(self, profile_id: str) -> dict:
        """Read only declared menu keys and digests, never rewrite a target."""
        profile = self._profile(profile_id)
        data = _read(profile["_config"])
        configured = {"configured_confirm": None, "independent_menu_controls_enabled": False
                      if profile.get("engine") == "ppsspp" else None, "configuration_effective": False}
        try:
            section, values = self._mapping(profile, "south")
            text = _configuration_text(data)
            keys = {key: (_assignment(text, section, key, ppsspp_ini=profile.get("engine") == "ppsspp") or {}).get("token")
                    for key in values}
            configured = self._configured_controls(profile, text)
            capability = True
        except SettingsError:
            keys, capability = {}, False
        if capability:
            try:
                current = self._profile(profile_id, writable=True)
                _require(current["_profile_hash"] == profile["_profile_hash"] and
                         _sha(_read(_under(self.profiles_dir, profile_id + ".json"))) == profile["_profile_hash"] and
                         _read(current["_config"]) == data,
                         "STALE_SNAPSHOT", "Menu configuration or profile changed during inspection")
                configured["configuration_effective"] = configured["configured_confirm"] is not None
            except SettingsError:
                pass
        return {"profile_id": profile_id, "generation": self._state()["generation"],
                "config_sha256": _sha(data), "qualified": profile.get("qualified") is True,
                "surface": profile.get("surface"), "menu_adapter_implemented": capability,
                "keys": keys, **configured, "gameplay_changed": False}

    def capabilities(self) -> dict:
        results = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            entry = {"profile_id": path.stem, "writable": False}
            try:
                profile = self._profile(path.stem, writable=True)
                self._mapping(profile, "south")
                configured = self._configured_controls(profile, _configuration_text(_read(profile["_config"])), qualified=True)
                entry.update(writable=True, surface=profile["surface"], **configured)
            except SettingsError as error:
                entry["error"] = error.as_dict()
            results.append(entry)
        return {"schema": 1, "generation": self._state()["generation"], "profiles": results}

    def preview(self, params: dict) -> dict:
        _fields(params, {"profile_id", "confirm", "expected_generation"},
                {"profile_id", "confirm", "expected_generation"})
        with _locked(self.lock):
            self._transactions().recover()
            profile = self._profile(params["profile_id"], writable=True)
            section, values = self._mapping(profile, params["confirm"])
            generation = _check_generation(params, self._state())
            data = _read(profile["_config"])
            text = _configuration_text(data)
            text, diff = self._menu_change(profile, text, section, values)
            _require(bool(diff), "NO_CHANGES", "Menu controls already match")
            preview_id = "preview-" + uuid.uuid4().hex
            record = {"schema": 1, "preview_id": preview_id, "profile_id": params["profile_id"],
                      "profile_sha256": profile["_profile_hash"], "generation": generation,
                      "config_sha256": _sha(data), "meta_sha256": _sha(_read(self.meta)),
                      "confirm": params["confirm"], "diff": diff}
            _atomic_write(self.previews / (preview_id + ".json"), _encoded(record))
            return {"preview_id": preview_id, "generation": generation, "profile_id": params["profile_id"],
                    "surface": profile["surface"], "diff": diff,
                    "after_configuration": self._configured_controls(profile, text, qualified=True),
                    "gameplay_changed": False}

    def apply(self, params: dict) -> dict:
        _fields(params, {"preview_id", "request_id", "expected_generation"},
                {"preview_id", "request_id", "expected_generation"})
        preview_id = _identifier(params["preview_id"], "preview ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "apply", preview_id)
            if replay is not None:
                return replay
            record = _json(self.previews / (preview_id + ".json"))
            _schema(record)
            profile = self._profile(record.get("profile_id"), writable=True)
            section, values = self._mapping(profile, record.get("confirm"))
            state = self._state()
            generation = _check_generation(params, state)
            data = _read(profile["_config"])
            _require(record.get("preview_id") == preview_id and record.get("generation") == generation and
                     record.get("config_sha256") == _sha(data) and record.get("meta_sha256") == _sha(_read(self.meta)) and
                     record.get("profile_sha256") == profile["_profile_hash"],
                     "STALE_SNAPSHOT", "Emulator configuration or profile changed since preview")
            text = _configuration_text(data)
            changes = record.get("diff")
            _require(isinstance(changes, list) and 0 < len(changes) <= len(values),
                     "INVALID_PREVIEW", "Invalid emulator menu diff")
            text, expected_changes = self._menu_change(profile, text, section, values)
            _require(_encoded(changes) == _encoded(expected_changes),
                     "INVALID_PREVIEW", "Preview must contain every required menu edit and no unowned edit")
            next_state = {**state, "generation": generation + 1}
            transaction_id = "tx-" + uuid.uuid4().hex
            result = {"transaction_id": transaction_id, "generation": generation + 1,
                      "profile_id": profile["id"], "surface": profile["surface"],
                      "applied": True, "idempotent": False,
                      **self._configured_controls(profile, text, qualified=True), "gameplay_changed": False}
            transactions.commit(transaction_id, request_id, "apply", preview_id,
                                [(profile["_config"], data, _configuration_bytes(text)),
                                 (self.meta, _read(self.meta), _encoded(next_state))],
                                {"profile_id": profile["id"], "diff": changes}, result)
            return result

    def undo(self, params: dict) -> dict:
        _fields(params, {"transaction_id", "request_id", "expected_generation"},
                {"transaction_id", "request_id", "expected_generation"})
        original_id = _identifier(params["transaction_id"], "transaction ID")
        request_id = _identifier(params["request_id"], "request ID")
        _generation(params["expected_generation"])
        with _locked(self.lock):
            transactions = self._transactions()
            transactions.recover()
            replay = transactions.replay(request_id, "undo", original_id)
            if replay is not None:
                return replay
            journal = transactions.journal(original_id)
            _require(journal["status"] == "committed" and journal.get("operation") == "apply",
                     "INVALID_TRANSACTION", "Only committed emulator changes can be undone")
            profile = self._profile(journal["metadata"]["profile_id"], writable=True)
            section, allowed = self._mapping(profile, "south")
            ppsspp_ini = profile.get("engine") == "ppsspp"
            state = self._state()
            generation = _check_generation(params, state)
            data = _read(profile["_config"])
            text = _configuration_text(data)
            after_snapshot = _configuration_text(transactions.snapshot(journal, 0, True))
            for item in journal["metadata"]["diff"]:
                key = item["key"]
                found = _assignment(text, section, key, ppsspp_ini=ppsspp_ini)
                _require(key in allowed and item["section"] == section and found is not None and
                         _semantic_token(found["token"], ppsspp_ini=ppsspp_ini,
                                         boolean=key == "IndependentMenuControls") == item["after"],
                         "UNDO_CONFLICT", "A menu setting was edited outside this transaction")
                if item["before_present"]:
                    text = set_config_token(text, key, item["before_token"], section=section, ppsspp_ini=ppsspp_ini)
                else:
                    original = _assignment(after_snapshot, section, key, ppsspp_ini=ppsspp_ini)
                    _require(original is not None and
                             text[found["line_start"]:found["line_end"]] ==
                             after_snapshot[original["line_start"]:original["line_end"]],
                             "UNDO_CONFLICT", "The inserted menu-setting line was edited externally")
                    text = text[:found["line_start"]] + text[found["line_end"]:]
            if data == transactions.snapshot(journal, 0, True):
                # With no external edit, restore exact pre-transaction bytes,
                # including a section header/newline added with the three keys.
                text = _configuration_text(transactions.snapshot(journal, 0))
            transaction_id = "tx-" + uuid.uuid4().hex
            result = {"transaction_id": transaction_id, "undone_transaction_id": original_id,
                      "generation": generation + 1, "profile_id": profile["id"],
                      "applied": True, "idempotent": False,
                      **self._configured_controls(profile, text, qualified=True), "gameplay_changed": False}
            next_state = {**state, "generation": generation + 1}
            transactions.commit(transaction_id, request_id, "undo", original_id,
                                [(profile["_config"], data, _configuration_bytes(text)),
                                 (self.meta, _read(self.meta), _encoded(next_state))],
                                {"profile_id": profile["id"], "undone_transaction_id": original_id}, result)
            return result

    def recover(self) -> None:
        with _locked(self.lock):
            self._transactions().recover()
