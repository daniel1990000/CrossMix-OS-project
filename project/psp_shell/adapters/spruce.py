# SPDX-License-Identifier: MIT
"""Original, bounded model facade for spruceOS 4.5.4 on the original Smart Pro.

No upstream code is imported or copied here. Snapshot reads never instantiate
PyUI's list managers: their constructors can rewrite/prune user lists. Live use
requires explicitly injected, existing PyUI managers and device callbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Callable, Iterable, Mapping
import unicodedata
import xml.etree.ElementTree as ElementTree


BASELINE = "d45ff8dfe5756147522b04ae5863d17a90e88b54"
DEVICE_NAMES = frozenset(("TRIMUI_A133P", "TRIMUI_SMART_PRO", "SPRUCE_TRIMUI_SMART_PRO"))
MAX_JSON = 1024 * 1024
MAX_ENTRIES = 50000
MAX_DEPTH = 12
MEDIA_SYSTEMS = frozenset(("MEDIA", "FFPLAY", "MPV", "MUSIC", "VIDEOS"))


class SpruceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _text(value: Any, name: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8", "surrogatepass")) > maximum or "\0" in value:
        raise SpruceError("INVALID_DATA", f"{name} must be bounded text")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise SpruceError("INVALID_UTF8", f"{name} is not valid UTF-8") from error
    return value


def _read_json(path: Path, default: Any = None, maximum: int = MAX_JSON) -> Any:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return default
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise SpruceError("INVALID_FILE", "Expected a bounded regular JSON file")
    try:
        # Do not follow a last-component symlink swapped in after lstat.
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            actual = os.fstat(stream.fileno())
            if not stat.S_ISREG(actual.st_mode):
                raise SpruceError("INVALID_FILE", "Expected a regular JSON file")
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise SpruceError("INPUT_TOO_LARGE", "JSON exceeded its size budget")
        value = json.loads(raw)
        stack = [(value, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > 32:
                raise SpruceError("INPUT_TOO_DEEP", "JSON nesting exceeded its limit")
            if isinstance(node, dict):
                stack.extend((child, depth + 1) for child in node.values())
            elif isinstance(node, list):
                stack.extend((child, depth + 1) for child in node)
        return value
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, SpruceError):
            raise
        raise SpruceError("INVALID_JSON", "Cannot read the JSON source") from error


def _sha_file(path: Path, maximum: int = 256 * 1024 * 1024) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise SpruceError("INVALID_FILE", "Fingerprint file is empty, special, or oversized")
        digest = hashlib.sha256()
        total = 0
        for chunk in iter(lambda: stream.read(65536), b""):
            total += len(chunk)
            if total > maximum:
                raise SpruceError("INPUT_TOO_LARGE", "Fingerprint file grew beyond its budget")
            digest.update(chunk)
        return digest.hexdigest()


def _under(root: Path, path: Path, *, exists: bool = True) -> Path:
    try:
        resolved = path.resolve(strict=exists)
        resolved.relative_to(root)
    except (ValueError, OSError, RuntimeError) as error:
        raise SpruceError("PATH_UNAVAILABLE", "Path is missing or escapes its approved root") from error
    return resolved


def _hash_id(kind: str, system: str, relative: str) -> str:
    return kind + ":" + hashlib.sha256((system + "\0" + relative).encode("utf-8")).hexdigest()


def _option_value(option: Any, basename: str) -> Any:
    if not isinstance(option, dict):
        return None
    overrides = option.get("overrides", {})
    if not isinstance(overrides, dict):
        raise SpruceError("INVALID_MANIFEST", "Preset overrides must be an object")
    return overrides.get(basename, option.get("selected"))


def _preset(config: dict, basename: str, requested: str | None = None) -> dict:
    options = config.get("menuOptions", {})
    if not isinstance(options, dict):
        raise SpruceError("INVALID_MANIFEST", "menuOptions must be an object")
    section = None
    if isinstance(options.get("Emulator_SmartPro"), dict):
        section = "Emulator_SmartPro"
    if section is None:
        for key, option in options.items():
            if key.startswith("Emulator") and isinstance(option, dict):
                devices = option.get("devices", [])
                if isinstance(devices, list) and DEVICE_NAMES.intersection(devices):
                    section = key
                    break
    if section is None:
        section = next((key for key in ("Emulator_64", "Emulator") if isinstance(options.get(key), dict)), None)
    choice = options.get(section, {}) if section else {}
    selected = _option_value(choice, basename)
    default = config.get("default_emulator")
    if not selected:
        selected = default
    if selected is not None:
        _text(selected, "selected emulator", 256)
    allowed = choice.get("options", []) if choice else []
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise SpruceError("INVALID_MANIFEST", "Emulator choices must be text entries")
    warnings = []
    repair_required = bool(selected and allowed and selected not in allowed)
    stored = selected
    if repair_required:
        warnings.append("SAVED_PRESET_UNAVAILABLE")
        base = choice.get("selected")
        selected = base if base in allowed else (default if default in allowed else allowed[0])
    if requested is not None:
        _text(requested, "preset_id", 256)
        if requested != selected and requested not in allowed:
            raise SpruceError("PRESET_UNAVAILABLE", "Requested emulator choice is unavailable")
    governor = _option_value(options.get("Governor", {}), basename)
    return {"preset_id": selected, "preset_section": section,
            "requested_preset": requested, "governor": governor,
            "choices": allowed, "warnings": warnings,
            "stored_preset": stored, "preset_repair_required": repair_required}


class SourceSnapshotProvider:
    """Read a card/source snapshot without writes, pruning, or executable calls."""

    live = False

    def __init__(self, sd_root: str | os.PathLike, *, max_entries: int = MAX_ENTRIES,
                 max_depth: int = MAX_DEPTH):
        self.root = Path(sd_root).resolve(strict=True)
        if not self.root.is_dir() or not 1 <= max_entries <= 1000000 or not 0 <= max_depth <= 32:
            raise SpruceError("INVALID_ROOT", "Snapshot root or scan limits are invalid")
        self.max_entries = max_entries
        self.max_depth = max_depth
        self.warnings: list[dict] = []
        self._systems: dict[str, dict] = {}
        self._games: dict[str, dict] = {}
        self._tools: dict[str, dict] = {}
        self._metadata: dict[str, dict] = {}
        self._loaded = False
        self._visited = 0

    def _warn(self, code: str, item: str = "") -> None:
        if len(self.warnings) < 256:
            self.warnings.append({"code": code, "id": item})

    def path(self, value: str | Path, base: Path | None = None, *, exists: bool = True) -> Path:
        raw = _text(str(value), "path")
        if raw == "/mnt/SDCARD" or raw.startswith("/mnt/SDCARD/"):
            candidate = self.root / raw[len("/mnt/SDCARD/"): ] if raw != "/mnt/SDCARD" else self.root
        else:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = (base or self.root) / candidate
        return _under(self.root, candidate, exists=exists)

    def _descriptor(self, path: Path) -> dict:
        value = _read_json(self.path(path), {})
        if not isinstance(value, dict):
            raise SpruceError("INVALID_MANIFEST", "Descriptor must contain an object")
        _text(value.get("label", path.parent.name), "label", 512)
        for key in ("launch", "extlist", "subfolder_launch_file"):
            if key in value:
                _text(value[key], key)
        return value

    def _supports(self, config: dict) -> bool:
        devices = config.get("devices", [])
        if not isinstance(devices, list) or not all(isinstance(item, str) for item in devices):
            raise SpruceError("INVALID_MANIFEST", "Descriptor devices must be text entries")
        return not devices or bool(DEVICE_NAMES.intersection(devices))

    def _required(self, config: dict) -> bool:
        groups = config.get("requiredfiles", [])
        if not isinstance(groups, list) or len(groups) > 64:
            raise SpruceError("INVALID_MANIFEST", "Required files must be a bounded group list")
        for group in groups:
            if not isinstance(group, list) or not group:
                raise SpruceError("INVALID_MANIFEST", "Required file group is invalid")
            present = False
            for item in group:
                try:
                    present = self.path(item).is_file() or present
                except SpruceError:
                    pass
            if not present:
                return False
        return True

    def _rom_roots(self, system: str, config: dict) -> list[Path]:
        aliases = config.get("alternativeFolderNames", [])
        if not isinstance(aliases, list) or len(aliases) > 64:
            raise SpruceError("INVALID_MANIFEST", "Alternate ROM folders must be a bounded list")
        roots = []
        seen = set()
        special = {"PORTS": "ports", "PPSSPP": "PSP", "FFPLAY": "FFMPEG", "MPV": "FFMPEG", "WSC": "WS"}
        for alias in [special.get(system, system), *aliases]:
            alias = _text(alias, "ROM folder", 256)
            if not alias or Path(alias).name != alias or alias in (".", ".."):
                raise SpruceError("INVALID_MANIFEST", "ROM folder name is invalid")
            try:
                folder = self.path(self.root / "Roms" / alias)
                if folder.is_dir() and folder not in seen:
                    roots.append(folder)
                    seen.add(folder)
            except SpruceError:
                continue
        return roots

    def _walk(self, folder: Path, config: dict, depth: int = 0,
              seen: set[Path] | None = None, approved_root: Path | None = None) -> Iterable[Path]:
        if depth > self.max_depth:
            self._warn("SCAN_DEPTH_LIMIT")
            return
        seen = seen if seen is not None else set()
        canonical = self.path(folder)
        approved_root = approved_root or canonical
        if not canonical.is_relative_to(approved_root):
            self._warn("ROM_ROOT_ESCAPE")
            return
        if canonical in seen:
            self._warn("SYMLINK_CYCLE")
            return
        seen.add(canonical)
        extensions = {"." + part.casefold() for part in config.get("extlist", "").split("|") if part}
        ignored = config.get("ignoreList", [])
        if not isinstance(ignored, list) or len(ignored) > 10000:
            raise SpruceError("INVALID_MANIFEST", "ignoreList is invalid")
        try:
            children = []
            with os.scandir(canonical) as iterator:
                for entry in iterator:
                    if len(children) + self._visited >= self.max_entries:
                        raise SpruceError("SCAN_LIMIT", "Snapshot entry limit reached")
                    children.append(entry)
            children.sort(key=lambda entry: entry.name)
        except OSError:
            self._warn("DIRECTORY_UNAVAILABLE")
            return
        for entry in children:
            self._visited += 1
            if self._visited > self.max_entries:
                raise SpruceError("SCAN_LIMIT", "Snapshot entry limit reached")
            try:
                name = _text(entry.name, "filename", 1024)
                if name.startswith(".") or name in ignored:
                    continue
                path = self.path(entry.path)
                if not path.is_relative_to(approved_root):
                    self._warn("ROM_ROOT_ESCAPE")
                    continue
                # Existing internal links work; outside-card links are rejected.
                if path.is_dir():
                    if config.get("scanSubfolders", True) and name != "Imgs":
                        launch_file = config.get("subfolder_launch_file")
                        if launch_file:
                            try:
                                special = self.path(path / launch_file)
                                if special.is_file():
                                    yield special
                                    continue
                            except SpruceError:
                                pass
                        yield from self._walk(path, config, depth + 1, seen, approved_root)
                elif path.is_file() and ((not extensions and path.suffix not in (".xml", ".txt", ".db")) or path.suffix.casefold() in extensions):
                    yield path
            except (SpruceError, OSError) as error:
                self._warn(getattr(error, "code", "PATH_UNAVAILABLE"))

    def _artwork(self, system: str, rom: Path, config: dict) -> str:
        supplied = self._metadata.get(str(rom), {}).get("artwork")
        if supplied:
            return supplied
        try:
            relative = rom.relative_to(self.root / "Roms")
        except ValueError:
            return ""
        stem = relative.with_suffix("")
        candidates = [self.root / "Roms" / relative.parts[0] / "Imgs" / Path(*stem.parts[1:]),
                      self.root / "Imgs" / stem,
                      self.root / "Saves" / "states" / ".gameswitcher" / (rom.stem + ".state.auto")]
        for candidate in candidates:
            for suffix in (".png", ".jpg", ".jpeg", ".qoi"):
                try:
                    path = self.path(str(candidate) + suffix)
                    if path.is_file():
                        return str(path)
                except SpruceError:
                    pass
        return ""

    def _load_metadata(self, folder: Path) -> None:
        """Bounded read-only counterpart for snapshot labels/art, not a writer."""
        for name in ("miyoogamelist.xml", "gamelist.xml"):
            path = folder / name
            if not path.exists():
                continue
            try:
                path = self.path(path)
                if path.stat().st_size > 2 * MAX_JSON:
                    raise SpruceError("INPUT_TOO_LARGE", "Gamelist exceeds the snapshot budget")
                with path.open("rb") as stream:
                    raw = stream.read(2 * MAX_JSON + 1)
                if len(raw) > 2 * MAX_JSON or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
                    raise SpruceError("INVALID_GAMELIST", "Gamelist entities or oversize input are not supported")
                tree = ElementTree.fromstring(raw.decode("utf-8"))
                if sum(1 for _ in tree.iter()) > 50000:
                    raise SpruceError("INPUT_TOO_LARGE", "Gamelist contains too many elements")
                for game in tree.findall("game"):
                    source_path = game.findtext("path")
                    if not source_path:
                        continue
                    try:
                        rom = self.path(source_path, folder)
                        # XML may name only a file in this approved ROM tree.
                        if not rom.is_relative_to(folder):
                            continue
                        metadata = {}
                        label = game.findtext("name")
                        if label:
                            metadata["label"] = _text(label, "gamelist name", 1024)
                        image = game.findtext("image")
                        if image:
                            try:
                                artwork = self.path(image, folder)
                                if artwork.is_file():
                                    metadata["artwork"] = str(artwork)
                            except SpruceError:
                                pass
                        self._metadata[str(rom)] = metadata
                    except SpruceError:
                        continue
            except (SpruceError, ElementTree.ParseError, OSError, UnicodeError) as error:
                self._warn(getattr(error, "code", "INVALID_GAMELIST"), folder.name)
            return # Same precedence as the existing manager: first present list.

    def _cache_metadata(self, folder: Path) -> dict:
        device_path = "/mnt/SDCARD/" + folder.relative_to(self.root).as_posix()
        filename = device_path.replace("/", "_").replace("\\", "_") + ".json"
        path = self.root / "Saves" / "cache" / filename
        try:
            cache = _read_json(path, None)
            if cache is None:
                return {"available": False, "authority": "rebuildable_cache"}
            if not isinstance(cache, dict) or not isinstance(cache.get("files"), list) or not isinstance(cache.get("folders"), list):
                raise SpruceError("INVALID_CACHE", "Snapshot cache metadata is malformed")
            return {"available": True, "authority": "rebuildable_cache", "source_mtime": cache.get("mtime"),
                    "cached_files": len(cache["files"]), "cached_folders": len(cache["folders"])}
        except SpruceError as error:
            return {"available": False, "authority": "rebuildable_cache", "warning": error.code}

    def game_record(self, system: str, rom_path: str | Path, *, label: str | None = None,
                    config: dict | None = None) -> dict:
        system = _text(system, "system_id", 256)
        if not system or Path(system).name != system or system in (".", ".."):
            raise SpruceError("INVALID_SYSTEM", "Invalid system identifier")
        if rom_path is None:
            raise SpruceError("ROM_UNAVAILABLE", "Game model has no ROM path")
        rom = self.path(rom_path)
        if not rom.is_file():
            raise SpruceError("ROM_UNAVAILABLE", "Game file is unavailable")
        config = config or self._descriptor(self.root / "Emu" / system / "config.json")
        if not any(rom.is_relative_to(folder) for folder in self._rom_roots(system, config)):
            raise SpruceError("ROM_ROOT_ESCAPE", "Game is outside this system's approved ROM folders")
        relative = rom.relative_to(self.root).as_posix()
        game_id = _hash_id("game", system, relative)
        selected = _preset(config, rom.name)
        artwork = self._artwork(system, rom, config)
        metadata_label = self._metadata.get(str(rom), {}).get("label")
        rendered_label = _text(label or metadata_label or rom.stem, "game label", 1024)
        return {"id": game_id, "game_id": game_id, "system_id": system,
                "relative_path": relative, "rom_path": str(rom),
                "label": rendered_label, "display_name": rendered_label,
                "metadata_label": bool(metadata_label),
                "extension": rom.suffix.lstrip(".").casefold(), "artwork": artwork,
                "artwork_ref": artwork, "availability": "available", "warnings": selected["warnings"],
                "selected_preset": selected["preset_id"], "governor": selected["governor"],
                "preset_repair_required": selected["preset_repair_required"],
                "capabilities": {"launch": False, "resume": False, "favorites_write": False},
                "source": "spruce", "source_baseline": BASELINE}

    def _load(self) -> None:
        if self._loaded:
            return
        self._visited = 0
        emu_root = self.root / "Emu"
        try:
            descriptors = sorted(emu_root.glob("*/config.json"))
        except OSError:
            descriptors = []
        for descriptor in descriptors:
            system = descriptor.parent.name
            if system.startswith((".", "-", "_")):
                continue
            try:
                config = self._descriptor(descriptor)
                if not self._supports(config):
                    continue
                if system in MEDIA_SYSTEMS:
                    self._tools["system:" + system] = {
                        "id": "system:" + system, "tool_id": "system:" + system,
                        "label": config.get("label", system), "description": "Existing media collection",
                        "availability": "legacy_only", "capabilities": {"launch": False},
                        "warnings": ["EXISTING_SPRUCE_ROUTE_REQUIRED"], "system_id": system}
                    continue
                roots = self._rom_roots(system, config)
                sort_order = config.get("sortOrder", 9999999)
                if type(sort_order) is not int:
                    sort_order = 9999999
                    self._warn("INVALID_SORT_ORDER", system)
                row = {"id": system, "system_id": system, "label": config.get("label", system),
                       "game_count": 0, "availability": "available", "warnings": [],
                       "rom_roots": [str(root) for root in roots], "sort_order": sort_order,
                       "cache_snapshots": [self._cache_metadata(root) for root in roots]}
                if not self._required(config):
                    row["availability"] = "missing_dependencies"
                    row["warnings"].append("REQUIRED_FILES_MISSING")
                collision_keys: dict[str, str] = {}
                seen_roms = set()
                for folder in roots:
                    self._load_metadata(folder)
                    for rom in self._walk(folder, config):
                        if rom in seen_roms:
                            continue
                        seen_roms.add(rom)
                        game = self.game_record(system, rom, config=config)
                        key = unicodedata.normalize("NFC", game["relative_path"]).casefold()
                        prior_id = collision_keys.get(key)
                        if prior_id:
                            for item in (game, self._games[prior_id]):
                                item["availability"] = "review_required"
                                item["warnings"].append("FILENAME_COLLISION")
                        else:
                            collision_keys[key] = game["id"]
                        if row["availability"] == "missing_dependencies":
                            game["availability"] = "missing_dependencies"
                        self._games[game["id"]] = game
                        row["game_count"] += 1
                if not roots:
                    row["availability"] = "missing_rom_root"
                elif not row["game_count"] and row["availability"] == "available":
                    row["availability"] = "empty"
                self._systems[system] = row
            except (SpruceError, OSError, TypeError) as error:
                self._warn(getattr(error, "code", "INVALID_MANIFEST"), system)
        self._load_tools()
        self._loaded = True

    def _load_tools(self) -> None:
        for descriptor in sorted((self.root / "App").glob("*/config.json")):
            name = descriptor.parent.name
            if name.startswith((".", "-", "_")):
                continue
            try:
                config = self._descriptor(descriptor)
                if not self._supports(config):
                    continue
                tool_id = "app:" + name
                available = False
                try:
                    launcher = self.path(config.get("launch", "launch.sh"), descriptor.parent)
                    available = launcher.is_file()
                except SpruceError:
                    pass
                self._tools[tool_id] = {"id": tool_id, "tool_id": tool_id,
                    "label": config.get("label", name), "description": _text(config.get("description", ""), "description", 4096),
                    "availability": "available" if available else "unavailable",
                    "capabilities": {"launch": False},
                    "warnings": ["SNAPSHOT_READ_ONLY"] + ([] if available else ["LAUNCHER_UNAVAILABLE"]),
                    "folder": str(descriptor.parent), "launch": config.get("launch", "launch.sh")}
            except (SpruceError, OSError, TypeError) as error:
                self._warn(getattr(error, "code", "INVALID_MANIFEST"), name)

    def systems(self) -> list[dict]:
        self._load()
        return sorted(self._systems.values(), key=lambda row: (row["sort_order"], row["label"].casefold()))

    def game_records(self, system_id: str | None = None) -> list[dict]:
        self._load()
        return [row.copy() for row in self._games.values() if system_id is None or row["system_id"] == system_id]

    def tools(self) -> list[dict]:
        self._load()
        return [row.copy() for row in self._tools.values()]

    def histories(self, name: str) -> list[dict]:
        self._load()
        filenames = {"favorites": "pyui-favorites.json", "recent": "pyui-recents.json", "switcher": "gameswitcher.json"}
        if name not in filenames:
            raise SpruceError("INVALID_HISTORY", "Unknown history list")
        path = self.root / "Saves" / filenames[name]
        try:
            records = _read_json(path, [], 8 * MAX_JSON)
            if not isinstance(records, list) or len(records) > 100000:
                raise SpruceError("INVALID_HISTORY", "History must be a bounded JSON array")
        except SpruceError as error:
            self._warn(error.code, name)
            return []
        index = {(game["system_id"], game["rom_path"]): game for game in self._games.values()}
        output, seen = [], set()
        for entry in records:
            if not isinstance(entry, dict):
                continue
            try:
                key = (_text(entry.get("game_system_name"), "system", 256),
                       str(self.path(entry.get("rom_file_path"))))
                game = index.get(key)
                if not game or game["id"] in seen:
                    continue
                seen.add(game["id"])
                item = game.copy()
                item["legacy_record"] = entry.copy()
                if entry.get("display_name") and not item.get("metadata_label"):
                    item["label"] = item["display_name"] = _text(entry["display_name"], "display_name", 1024)
                output.append(item)
            except (SpruceError, TypeError):
                continue
        return output

    def resolve_game(self, game: dict, preset_id: str | None, mode: str) -> dict:
        system = game["system_id"]
        config = self._descriptor(self.root / "Emu" / system / "config.json")
        rom = self.path(game["rom_path"])
        if not rom.is_file():
            raise SpruceError("ROM_UNAVAILABLE", "Game file is unavailable")
        selected = _preset(config, rom.name, preset_id)
        raw_launch = _text(config.get("launch", ""), "launcher")
        if not raw_launch:
            raise SpruceError("LAUNCHER_UNAVAILABLE", "Descriptor has no launcher")
        emu_dir = self.path(self.root / "Emu" / system)
        canonical = self.path(raw_launch, emu_dir)
        if not canonical.is_file():
            raise SpruceError("LAUNCHER_UNAVAILABLE", "Game launcher is unavailable")
        # Keep .. in the executable spelling. standard_launch.sh reads $0.
        if raw_launch.startswith("/mnt/SDCARD/"):
            lexical = str(self.root) + raw_launch[len("/mnt/SDCARD"):]
        elif Path(raw_launch).is_absolute():
            lexical = raw_launch
        else:
            lexical = str(emu_dir) + "/" + raw_launch
        return {"schema": 1, "game_id": game["id"], "system_id": system, "label": game["label"],
                "rom_path": str(rom), "mode": mode, **selected,
                "executable": lexical, "canonical_executable": str(canonical),
                "argv": [lexical, str(rom)], "cwd": str(emu_dir), "environment": {},
                "launchable": False, "gate_reason": "SNAPSHOT_READ_ONLY", "profile_id": "spruce-4.5.4-tg5040"}

    def resolve_tool(self, tool: dict) -> dict:
        if not tool["id"].startswith("app:"):
            raise SpruceError("EXISTING_SPRUCE_ROUTE_REQUIRED", "Open this collection through its existing Spruce route")
        folder = self.path(tool["folder"])
        canonical = self.path(tool["launch"], folder)
        return {"tool_id": tool["id"], "label": tool["label"], "executable": str(folder) + "/" + tool["launch"],
                "canonical_executable": str(canonical), "argv": [], "cwd": str(folder),
                "mode": "normal", "launchable": False, "gate_reason": "SNAPSHOT_READ_ONLY"}


class PyUIModelProvider(SourceSnapshotProvider):
    """Use injected PyUI objects, never instantiate a second data authority.

    system_manager.get_active_systems() and game_list(system_id) supply current
    GameSystem/RomInfo objects. device.run_game(rom_info) remains the game path.
    Optional tool callbacks are installed by ID by the trusted bootstrap.
    """

    live = True

    def __init__(self, sd_root: str | os.PathLike, *, system_manager: Any,
                 game_list: Callable[[str], Iterable], device: Any,
                 favorites_manager: Any, recents_manager: Any,
                 release_resources: Callable[[], Any], quiescent: Callable[[], bool],
                 tool_list: Callable[[], Iterable[dict]] | None = None,
                 tool_actions: Mapping[str, Callable] | None = None,
                 mode_actions: Mapping[str, Mapping[str, Callable]] | None = None,
                 label_for: Callable[[Any], str] | None = None,
                 artwork_for: Callable[[Any], str | None] | None = None):
        super().__init__(sd_root)
        if not callable(game_list) or not callable(release_resources) or not callable(quiescent):
            raise SpruceError("INVALID_PROVIDER", "Live provider needs explicit model and lifecycle callbacks")
        if not callable(getattr(system_manager, "get_active_systems", None)) or not callable(getattr(device, "run_game", None)):
            raise SpruceError("INVALID_PROVIDER", "Live provider needs existing PyUI system and device managers")
        self.system_manager, self.game_list, self.device = system_manager, game_list, device
        self.favorites_manager, self.recents_manager = favorites_manager, recents_manager
        self.release_resources, self.quiescent = release_resources, quiescent
        self.tool_list, self.tool_actions = tool_list, dict(tool_actions or {})
        self.mode_actions = dict(mode_actions or {})
        self.label_for, self.artwork_for = label_for, artwork_for
        self.models: dict[str, Any] = {}

    @classmethod
    def from_pyui(cls, sd_root: str | os.PathLike, *, device: Any,
                  release_resources: Callable[[], Any], quiescent: Callable[[], bool],
                  tool_list: Callable[[], Iterable[dict]] | None = None,
                  tool_actions: Mapping[str, Callable] | None = None,
                  mode_actions: Mapping[str, Mapping[str, Callable]] | None = None) -> "PyUIModelProvider":
        """Bind the already-running pinned PyUI managers, without starting them.

        Call after PyUI's normal background manager initialization has completed.
        Imports are fixed package names, never supplied by card/ROM metadata.
        """
        from menus.games.utils.favorites_manager import FavoritesManager
        from menus.games.utils.recents_manager import RecentsManager
        from menus.games.utils.rom_info import RomInfo
        from menus.games.utils.rom_select_options_builder import get_rom_select_options_builder

        for manager in (FavoritesManager, RecentsManager):
            ready = getattr(manager, "_init_event", None)
            if ready is None or not ready.is_set():
                raise SpruceError("MODELS_NOT_READY", "Wait for the existing PyUI managers to finish startup")
        systems = device.get_game_system_utils()
        builder = get_rom_select_options_builder()
        rom_utils = builder.rom_utils

        def game_list(system_id: str):
            game_system = systems.get_game_system_by_name(system_id)
            if game_system is None:
                return
            queue = [(None, 0)]
            visited, count = set(), 0
            while queue:
                directory, depth = queue.pop()
                marker = os.path.realpath(directory) if directory else "<root>"
                if marker in visited or depth > MAX_DEPTH:
                    continue
                visited.add(marker)
                files, folders = rom_utils.get_roms(game_system, directory)
                for filename in files:
                    count += 1
                    if count > MAX_ENTRIES:
                        raise SpruceError("MODEL_LIMIT", "Existing ROM manager exceeded the query budget")
                    yield RomInfo(game_system, filename)
                queue.extend((folder, depth + 1) for folder in folders)

        return cls(sd_root, system_manager=systems, game_list=game_list, device=device,
                   favorites_manager=FavoritesManager, recents_manager=RecentsManager,
                   release_resources=release_resources, quiescent=quiescent,
                   tool_list=tool_list, tool_actions=tool_actions, mode_actions=mode_actions,
                   label_for=builder.resolve_display_name, artwork_for=builder.get_image_path)

    def systems(self) -> list[dict]:
        output = []
        for model in self.system_manager.get_active_systems():
            name = getattr(model, "system_name", None)
            if not name:
                name = getattr(getattr(model, "game_system_config", None), "system_name", None)
            name = _text(name, "system_id", 256)
            config = self._descriptor(self.root / "Emu" / name / "config.json")
            if self._supports(config) and name not in MEDIA_SYSTEMS:
                output.append({"id": name, "system_id": name,
                    "label": getattr(model, "display_name", config.get("label", name)),
                    "game_count": None, "availability": "available", "warnings": []})
        return output

    def _record_model(self, model: Any) -> dict:
        game_system = getattr(model, "game_system", None)
        name = getattr(game_system, "system_name", None)
        if not name:
            name = getattr(getattr(game_system, "game_system_config", None), "system_name", None)
        label = self.label_for(model) if self.label_for else getattr(model, "display_name", None)
        record = self.game_record(name, getattr(model, "rom_file_path", None), label=label)
        if self.artwork_for:
            artwork = self.artwork_for(model)
            if artwork:
                try:
                    record["artwork"] = record["artwork_ref"] = str(self.path(artwork))
                except SpruceError:
                    record["warnings"].append("ARTWORK_OUTSIDE_SNAPSHOT")
        self.models[record["id"]] = model
        record["capabilities"]["launch"] = True
        return record

    def game_records(self, system_id: str | None = None) -> list[dict]:
        names = [system_id] if system_id else [row["id"] for row in self.systems()]
        output = []
        seen, collisions = set(), {}
        for name in names:
            for model in self.game_list(name):
                if len(output) >= self.max_entries:
                    raise SpruceError("MODEL_LIMIT", "Live model query exceeded its budget")
                record = self._record_model(model)
                if record["id"] in seen:
                    continue
                seen.add(record["id"])
                key = (record["system_id"], unicodedata.normalize("NFC", record["relative_path"]).casefold())
                if key in collisions:
                    for item in (record, collisions[key]):
                        item["availability"] = "review_required"
                        item["capabilities"]["launch"] = False
                        if "FILENAME_COLLISION" not in item["warnings"]:
                            item["warnings"].append("FILENAME_COLLISION")
                else:
                    collisions[key] = record
                output.append(record)
        return output

    def histories(self, name: str) -> list[dict]:
        if name == "favorites":
            values = self.favorites_manager.get_favorites()
        elif name == "recent":
            values = self.recents_manager.get_recents()
        else:
            return super().histories(name)
        output = []
        for model in values:
            try:
                output.append(self._record_model(model))
            except (SpruceError, OSError):
                continue
        return output

    def tools(self) -> list[dict]:
        if self.tool_list is None:
            return super().tools()
        output = []
        for raw in self.tool_list():
            if not isinstance(raw, dict):
                raise SpruceError("INVALID_PROVIDER", "Injected tools must be normalized objects")
            tool = raw.copy()
            tool_id = _text(tool.get("id", tool.get("tool_id")), "tool_id", 512)
            tool.update({"id": tool_id, "tool_id": tool_id, "capabilities": {"launch": callable(self.tool_actions.get(tool_id))}})
            output.append(tool)
        return output


@dataclass
class _Action:
    kind: str
    item_id: str
    mode: str
    callback: Callable
    identity: tuple


class SpruceBackend:
    """Normalized shell-facing API with explicit, in-process live actions."""

    def __init__(self, sd_root: str | os.PathLike, read_only: bool = True, managers: Any = None):
        if isinstance(managers, Mapping):
            managers = PyUIModelProvider(sd_root, **dict(managers))
        if managers is not None and not isinstance(managers, (SourceSnapshotProvider, PyUIModelProvider)):
            raise SpruceError("INVALID_PROVIDER", "Use an explicit Spruce model provider")
        self.provider = managers or SourceSnapshotProvider(sd_root)
        self.read_only = bool(read_only)
        self._actions: dict[str, _Action] = {}
        self._resume_records: dict[str, dict] = {}
        self._engine_profiles: dict[str, dict] = {}

    def systems(self) -> list[dict]:
        return self.provider.systems()

    def games(self, system_id: str | None = None, search: str = "", offset: int = 0, limit: int = 50) -> dict:
        if type(offset) is not int or type(limit) is not int or offset < 0 or offset > MAX_ENTRIES or not 1 <= limit <= 200:
            raise SpruceError("INVALID_QUERY", "Pagination exceeds its bounds")
        search = _text(search, "search", 1024).casefold()
        if system_id is not None:
            _text(system_id, "system_id", 256)
        rows = self.provider.game_records(system_id)
        rows = [row for row in rows if search in row["label"].casefold()]
        rows.sort(key=lambda row: (row["label"].casefold(), row["id"]))
        return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit}

    def tools(self) -> list[dict]:
        return self.provider.tools()

    def _game(self, game_id: str) -> dict:
        _text(game_id, "game_id", 128)
        for row in self.provider.game_records():
            if row["id"] == game_id:
                return row
        raise SpruceError("GAME_NOT_FOUND", "Game is no longer in the current library")

    def favorites(self) -> list[dict]:
        return [dict(row, favorite=True) for row in self.provider.histories("favorites")]

    def recent(self) -> list[dict]:
        return [dict(row, **self._resume_status(row)) for row in self.provider.histories("recent")]

    def set_resume_evidence(self, records: Mapping[str, dict], engine_profiles: Mapping[str, dict]) -> None:
        """Install trusted lifecycle evidence/profile mappings; never ROM metadata."""
        if not isinstance(records, Mapping) or not isinstance(engine_profiles, Mapping) or len(records) > 10000:
            raise SpruceError("INVALID_RESUME_EVIDENCE", "Resume evidence must be bounded mappings")
        if not all(isinstance(key, str) and isinstance(value, dict) for key, value in records.items()) or not all(
                isinstance(key, str) and isinstance(value, dict) for key, value in engine_profiles.items()):
            raise SpruceError("INVALID_RESUME_EVIDENCE", "Resume records and engine profiles must be objects")
        try:
            encoded = json.dumps([dict(records), dict(engine_profiles)], allow_nan=False)
            if len(encoded.encode("utf-8")) > 8 * MAX_JSON:
                raise SpruceError("INVALID_RESUME_EVIDENCE", "Resume evidence exceeded its input budget")
            self._resume_records, self._engine_profiles = json.loads(encoded)
        except (ValueError, TypeError, RecursionError, UnicodeError) as error:
            if isinstance(error, SpruceError):
                raise
            raise SpruceError("INVALID_RESUME_EVIDENCE", "Resume evidence is not bounded JSON data") from error
        # A previously minted resume action must not outlive its evidence generation.
        self._actions = {key: action for key, action in self._actions.items() if action.mode != "resume"}

    def _resume_status(self, game: dict) -> dict:
        result = {"resume_available": False, "resume_eligible": False,
                  "resume_reason": "NO_VERIFIED_STATE", "continue_kind": "recently_played"}
        record = self._resume_records.get(game["id"])
        if not record:
            return result
        try:
            if record.get("schema") != 1 or record.get("game_id") != game["id"] or record.get("clean_shutdown") is not True:
                raise SpruceError("UNCLEAN_OR_WRONG_GAME", "Resume evidence does not identify a clean game session")
            profile = self._engine_profiles.get(game.get("selected_preset"))
            if not isinstance(profile, dict):
                raise SpruceError("UNKNOWN_ENGINE", "No verified engine profile is installed")
            if record.get("engine_id") != profile.get("engine_id") or record.get("engine_sha256") != profile.get("sha256"):
                raise SpruceError("ENGINE_CHANGED", "State belongs to another engine")
            if profile.get("architecture", "aarch64") != "aarch64":
                raise SpruceError("ARCHITECTURE_MISMATCH", "State belongs to another architecture")
            engine = self.provider.path(profile["executable"])
            if _sha_file(engine) != profile.get("sha256"):
                raise SpruceError("ENGINE_CHANGED", "Installed engine fingerprint changed")
            state_info = record.get("state", {})
            if not isinstance(state_info, dict) or not profile.get("state_format_id") or state_info.get("format_id") != profile["state_format_id"]:
                raise SpruceError("STATE_FORMAT_MISMATCH", "State format is not verified")
            slot = state_info.get("slot")
            if type(slot) is not int or not 0 <= slot <= 99:
                raise SpruceError("INVALID_STATE_SLOT", "State slot is invalid")
            state_path = self.provider.path(state_info["path"])
            roots = profile.get("state_roots", [])
            if not isinstance(roots, list) or not any(state_path.is_relative_to(self.provider.path(root)) for root in roots):
                raise SpruceError("STATE_PATH_REJECTED", "State is outside verified engine state roots")
            if _sha_file(state_path) != state_info.get("sha256"):
                raise SpruceError("STATE_CHANGED", "State file is missing or changed")
            result["resume_eligible"] = True
            result["resume_reason"] = "VERIFIED_STATE_NO_ACTION"
            if isinstance(self.provider, PyUIModelProvider) and not self.read_only:
                handler = self.provider.mode_actions.get(game["selected_preset"], {}).get("resume")
                if callable(handler):
                    result.update(resume_available=True, resume_reason="VERIFIED_STATE", continue_kind="resume")
        except (SpruceError, KeyError, TypeError, OSError) as error:
            result["resume_reason"] = getattr(error, "code", "INVALID_RESUME_EVIDENCE")
        return result

    def _identity(self, game: dict) -> tuple:
        rom = self.provider.path(game["rom_path"])
        descriptor = self.provider.path(self.provider.root / "Emu" / game["system_id"] / "config.json")
        info = rom.stat()
        return (str(rom), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, _sha_file(descriptor, MAX_JSON))

    def resolve_game(self, game_id: str, preset_id: str | None = None, mode: str = "normal") -> dict:
        if mode not in ("normal", "fresh", "resume"):
            raise SpruceError("INVALID_MODE", "Unknown launch mode")
        game = self._game(game_id)
        context = self.provider.resolve_game(game, preset_id, mode)
        context.update(self._resume_status(game))
        if game["availability"] != "available":
            context["gate_reason"] = "GAME_REQUIRES_REVIEW"
            return context
        if not isinstance(self.provider, PyUIModelProvider) or self.read_only:
            return context
        if context["preset_repair_required"]:
            context["gate_reason"] = "SAVED_PRESET_UNAVAILABLE"
            return context
        if preset_id is not None and preset_id != context["preset_id"]:
            context["gate_reason"] = "PRESET_REQUIRES_EXISTING_MENU"
            return context
        model = self.provider.models.get(game_id)
        callback = (lambda: self.provider.device.run_game(model)) if mode == "normal" else None
        if mode != "normal":
            handler = self.provider.mode_actions.get(context["preset_id"], {}).get(mode)
            if mode == "resume" and not context["resume_available"]:
                context["gate_reason"] = "RESUME_UNAVAILABLE"
                return context
            if callable(handler):
                evidence = self._resume_records.get(game_id)
                callback = lambda: handler(model, evidence)
        if not model or not callable(callback):
            context["gate_reason"] = "UNSUPPORTED_LAUNCH_MODE"
            return context
        if len(self._actions) >= 64:
            self._actions.clear()
        token = "game:" + secrets.token_hex(16)
        self._actions[token] = _Action("game", game_id, mode, callback, self._identity(game))
        context.update(action_id=token, launchable=True, gate_reason="")
        return context

    def resolve_tool(self, tool_id: str) -> dict:
        _text(tool_id, "tool_id", 512)
        tool = next((item for item in self.tools() if item["id"] == tool_id), None)
        if tool is None:
            raise SpruceError("TOOL_NOT_FOUND", "Tool is not in the current registry")
        if not isinstance(self.provider, PyUIModelProvider) or self.read_only:
            return self.provider.resolve_tool(tool)
        callback = self.provider.tool_actions.get(tool_id)
        if not callable(callback):
            return {"tool_id": tool_id, "label": tool["label"], "launchable": False,
                    "gate_reason": "EXISTING_SPRUCE_ROUTE_REQUIRED"}
        if len(self._actions) >= 64:
            self._actions.clear()
        token = "tool:" + secrets.token_hex(16)
        self._actions[token] = _Action("tool", tool_id, "normal", callback, ())
        return {"tool_id": tool_id, "label": tool["label"], "launchable": True, "gate_reason": "", "action_id": token}

    def validate_action(self, action_id: str, mode: str | None = None) -> None:
        if self.read_only or not isinstance(self.provider, PyUIModelProvider):
            raise SpruceError("SNAPSHOT_READ_ONLY", "This source snapshot cannot execute device actions")
        _text(action_id, "action_id", 128)
        action = self._actions.get(action_id)
        if action is None:
            raise SpruceError("UNKNOWN_ACTION", "Action token is unknown or was already consumed")
        if mode is not None and mode != action.mode:
            raise SpruceError("ACTION_MODE_MISMATCH", "Action was resolved for another launch mode")
        if not self.provider.quiescent():
            raise SpruceError("BUSY_SESSION", "Wait for the existing foreground job to finish")
        if action.kind == "game" and self._identity(self._game(action.item_id)) != action.identity:
            raise SpruceError("STALE_ACTION", "The game or selected settings changed after preview")
        if action.mode == "resume" and not self._resume_status(self._game(action.item_id))["resume_available"]:
            raise SpruceError("RESUME_UNAVAILABLE", "State eligibility changed after preview")

    def execute_action(self, action_id: str, mode: str | None = None, *, release_ui: bool = True) -> Any:
        """Invoke one registered callback; Coordinator passes release_ui=False."""
        self.validate_action(action_id, mode)
        action = self._actions.pop(action_id)
        if release_ui:
            self.provider.release_resources()
        return action.callback()

    def preview_favorite(self, game_id: str, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise SpruceError("INVALID_PARAMS", "Favorite selection must be a boolean")
        game = self._game(game_id)
        current = any(item["id"] == game_id for item in self.favorites())
        supported = isinstance(self.provider, PyUIModelProvider) and not self.read_only
        return {"game_id": game_id, "label": game["label"], "before": current, "after": enabled,
                "supported": supported, "gate_reason": "" if supported else "SNAPSHOT_READ_ONLY",
                "identity": list(self._identity(game))}

    def set_favorite(self, game_id: str, enabled: bool, preview: dict | None = None) -> None:
        current = self.preview_favorite(game_id, enabled)
        if not current["supported"]:
            raise SpruceError("SNAPSHOT_READ_ONLY", "Favorites can only change through the existing PyUI manager")
        if not self.provider.quiescent():
            raise SpruceError("BUSY_SESSION", "Favorites require an idle existing session")
        if preview is not None and preview != current:
            raise SpruceError("STALE_PREVIEW", "Favorite source changed after preview")
        model = self.provider.models.get(game_id)
        if model is None:
            raise SpruceError("MODEL_UNAVAILABLE", "Existing PyUI game model is unavailable")
        manager = self.provider.favorites_manager
        if enabled:
            manager.add_favorite(model)
        else:
            manager.remove_favorite(model)
