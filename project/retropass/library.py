"""Portable translations of RetroPass playlist and EmulationStation metadata.

SPDX-License-Identifier: GPL-2.0-only

Derived from Playlist.cs (UpdateGamesLandingPage) and
DataSourceEmulationStation.cs (GameES/SystemListEmulatorsES/Load) at the upstream
commit recorded in NOTICE.txt. Windows Storage and DLL-only assumptions are
replaced by bounded, read-only XML parsing and Linux paths. ROM identity rather
than the displayed title identifies recents, so same-title games stay distinct.
This module never runs an emulator command or writes a library or game file.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from typing import Any, Callable, Iterable, Mapping, TypeVar
import xml.etree.ElementTree as ET

from .layout import LANDING_LIMIT


T = TypeVar("T")
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_XML_ENTRIES = 50000


class XMLLimitError(ValueError):
    """An XML input exceeded the configured byte or all-element budget."""


def _identifier(item: Any) -> str:
    value = item.get("game_id", item.get("id", "")) if isinstance(item, Mapping) else getattr(item, "id", "")
    if not isinstance(value, str) or not value:
        raise ValueError("A RetroPass playlist item needs a stable game ID")
    return value


def landing_items(items: Iterable[T], recent_ids: Iterable[str], limit: int = LANDING_LIMIT) -> tuple[T, ...]:
    """Port the upstream recent-first, distinct, five-item landing selection.

    Input order supplies the fallback just as PlaylistItems.Take(5) does in
    RetroPass. Stale recent IDs are ignored; all distinct fallback items may be
    used so duplicates cannot leave a short row when more games are available.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= MAX_XML_ENTRIES:
        raise ValueError("Playlist limit is outside the supported range")
    if limit == 0:
        return ()
    ordered: dict[str, T] = {}
    for item in items:
        ordered.setdefault(_identifier(item), item)
    selected: dict[str, T] = {}
    for identifier in recent_ids:
        if identifier in ordered:
            selected.setdefault(identifier, ordered[identifier])
            if len(selected) == limit:
                return tuple(selected.values())
    for identifier, item in ordered.items():
        selected.setdefault(identifier, item)
        if len(selected) == limit:
            break
    return tuple(selected.values())


def core_name(command: str) -> str:
    """Extract the upstream core basename, accepting Linux .so and Xbox .dll.

    Commands are metadata only. Do not interpret substitutions or execute them.
    """
    if not isinstance(command, str):
        raise ValueError("An emulator command must be text")
    match = re.search(r'''([^/\\\s"'<>|;&]+\.(?:so|dll))(?=[\s"']|$)''', command, re.IGNORECASE)
    return match.group(1) if match else ""


@dataclass(frozen=True)
class ESSystem:
    name: str
    fullname: str
    path: str
    command: str

    @property
    def core_name(self) -> str:
        return core_name(self.command)


@dataclass(frozen=True)
class ESGame:
    id: str
    title: str
    system_id: str
    system_label: str
    path: str
    thumbnail: str = ""
    screenshot: str = ""
    video: str = ""
    description: str = ""
    release_date: str = ""
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    core_name: str = ""
    title_supplied: bool = False

    @property
    def artwork(self) -> str:
        # GameES.Init prefers Thumbnail and falls back to Screenshot.
        return self.thumbnail or self.screenshot

    def to_record(self) -> dict[str, str]:
        """Return display metadata; native launch routing remains elsewhere."""
        return {"game_id": self.id, "display_name": self.title,
                "system_id": self.system_id, "system_label": self.system_label,
                "artwork_ref": self.artwork, "description": self.description,
                "developer": self.developer, "publisher": self.publisher,
                "genre": self.genre, "release_date": self.release_date}


def _xml(path: Path, expected: str, max_bytes: int = MAX_XML_BYTES) -> ET.Element:
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_XML_BYTES:
        raise ValueError("Invalid XML metadata byte budget")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("EmulationStation XML must be a regular file")
        if info.st_size > max_bytes:
            raise XMLLimitError("EmulationStation XML exceeds the metadata size limit")
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise XMLLimitError("EmulationStation XML exceeds the metadata size limit")
    # XML entity declarations are not needed for the ES data model; reject them
    # before parsing, including UTF-16/32 encodings with embedded zero bytes.
    normalized = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in normalized or b"<!ENTITY" in normalized:
        raise ValueError("EmulationStation XML declarations are unsupported")
    try:
        result = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Invalid EmulationStation XML") from exc
    if result.tag != expected:
        raise ValueError("Unexpected EmulationStation XML root")
    if sum(1 for _ in result.iter()) > MAX_XML_ENTRIES:
        raise XMLLimitError("EmulationStation XML exceeds the all-element limit")
    return result


def _text(element: ET.Element, tag: str) -> str:
    return (element.findtext(tag) or "").strip()


def parse_systems(path: str | Path) -> tuple[ESSystem, ...]:
    """Read the same systemList/name/fullname/path/command schema as RetroPass."""
    root = _xml(Path(path), "systemList")
    systems: dict[str, ESSystem] = {}
    for node in root.findall("system"):
        name = _text(node, "name")
        if name:
            systems.setdefault(name, ESSystem(name, _text(node, "fullname") or name,
                                             _text(node, "path"), _text(node, "command")))
    return tuple(systems.values())


def _path(value: str, base: Path, root: Path,
          path_resolver: Callable[[str], str | Path] | None = None) -> str:
    if not value:
        return ""
    # Imported metadata may originate on Windows; portable relative separators
    # work, while drive/UNC paths require an explicit remap outside this parser.
    windows = PureWindowsPath(value)
    if windows.drive:
        raise ValueError("Windows absolute metadata paths require a Linux remap")
    if path_resolver is not None:
        candidate = Path(path_resolver(value.replace("\\", "/"))).resolve()
    else:
        candidate = Path(value.replace("\\", "/"))
        candidate = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("EmulationStation metadata path is outside the supplied root") from exc
    return str(candidate)


def parse_gamelist(path: str | Path, *, system_id: str | None = None,
                   system_label: str = "", command: str = "",
                   root: str | Path | None = None, max_bytes: int = MAX_XML_BYTES,
                   skip_invalid_entries: bool = False,
                   path_resolver: Callable[[str], str | Path] | None = None) -> tuple[ESGame, ...]:
    """Read a gamelist into immutable metadata, sorted as Playlist.Sort does.

    Relative paths resolve against the gamelist's own directory (the portable
    ES convention), rather than RetroPass's Xbox datasource root. ``root`` can
    name a broader card/library root; every ROM and media path must stay inside
    it. Missing ROMs remain metadata and are never tested by executing scripts.
    Existing snapshot readers may inject their native mount-path resolver and
    use ``skip_invalid_entries``: an invalid ROM is ignored and invalid optional
    media is omitted without losing other valid records. Limits still reject
    the entire XML input before any metadata is returned.
    """
    path = Path(path).resolve()
    base = path.parent
    root = Path(root).resolve() if root is not None else base
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("The gamelist must be inside the supplied root") from exc
    system_id = system_id or base.name
    if not isinstance(system_id, str) or not system_id:
        raise ValueError("A gamelist needs a system ID")
    result: dict[str, ESGame] = {}
    core = core_name(command)
    def resolve(value: str, *, optional: bool = False) -> str:
        try:
            return _path(value, base, root, path_resolver)
        except (ValueError, OSError, RuntimeError):
            if skip_invalid_entries and optional:
                return ""
            raise

    for node in _xml(path, "gameList", max_bytes).findall("game"):
        value = _text(node, "path")
        if not value:
            continue
        try:
            rom = resolve(value)
        except (ValueError, OSError, RuntimeError):
            if skip_invalid_entries:
                continue
            raise
        relative = Path(rom).relative_to(root).as_posix()
        identity = json.dumps([system_id, relative], ensure_ascii=False, separators=(",", ":"))
        identifier = "retropass-es:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        result.setdefault(identifier, ESGame(
            id=identifier, title=_text(node, "name") or Path(rom).stem,
            system_id=system_id, system_label=system_label or system_id, path=rom,
            thumbnail=resolve(_text(node, "thumbnail"), optional=True),
            screenshot=resolve(_text(node, "image"), optional=True),
            video=resolve(_text(node, "video"), optional=True),
            description=_text(node, "desc"), release_date=_text(node, "releasedate"),
            developer=_text(node, "developer"), publisher=_text(node, "publisher"),
            genre=_text(node, "genre"), core_name=core,
            title_supplied=bool(_text(node, "name"))))
    return tuple(sorted(result.values(), key=lambda game: (game.title.casefold(), game.id)))
