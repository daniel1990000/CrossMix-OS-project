# SPDX-License-Identifier: MIT
"""Read-only, bounded inspection of existing PS1 disc references.

The launcher and selected emulator remain authoritative. This module neither
creates playlists nor discovers save or memory-card paths. A PBP's internal
disc table is deliberately left to the existing native emulator.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat


PS1_SYSTEMS = frozenset(("PS", "PS1", "PSX", "PLAYSTATION"))
MAX_PLAYLIST_BYTES = 65536
MAX_PLAYLIST_ENTRIES = 128
DISC_EXTENSIONS = frozenset((".cue", ".chd", ".pbp", ".bin", ".iso", ".img", ".ccd", ".mdf"))


class _InspectionError(ValueError):
    pass


def _open_regular(root: Path, path: Path) -> int:
    """Open a resolved card path without following swapped ancestor symlinks."""
    relative = path.relative_to(root)
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    directory_fd = os.open(root.anchor, directory_flags)
    try:
        # Root and reference paths were resolved before inspection. Walk every
        # component through held descriptors so a later rename/symlink swap
        # cannot redirect a read outside that tree.
        for component in (*root.parts[1:], *relative.parts[:-1]):
            child_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        fd = os.open(relative.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory_fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise _InspectionError("DISC_REFERENCE_TOO_LARGE_OR_SPECIAL")
        except BaseException:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(directory_fd)


def _read_text(root: Path, path: Path) -> str:
    """Never follow swapped symlinks or block on a device/FIFO."""
    fd = _open_regular(root, path)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PLAYLIST_BYTES:
            raise _InspectionError("DISC_REFERENCE_TOO_LARGE_OR_SPECIAL")
        raw = stream.read(MAX_PLAYLIST_BYTES + 1)
    if len(raw) > MAX_PLAYLIST_BYTES:
        raise _InspectionError("DISC_REFERENCE_TOO_LARGE_OR_SPECIAL")
    text = raw.decode("utf-8-sig")
    if "\0" in text:
        raise _InspectionError("INVALID_DISC_REFERENCE_TEXT")
    return text


def _path(root: Path, parent: Path, raw: str) -> tuple[Path, str]:
    if not raw or len(raw) > 4096 or any(ord(char) < 32 for char in raw):
        raise _InspectionError("INVALID_DISC_PATH")
    # Existing playlists may use Windows separators or the device mount path.
    raw = raw.replace("\\", "/")
    if "://" in raw or re.match(r"^[A-Za-z]:", raw):
        raise _InspectionError("DISC_PATH_OUTSIDE_CARD")
    if raw == "/mnt/SDCARD" or raw.startswith("/mnt/SDCARD/"):
        candidate = root / raw.removeprefix("/mnt/SDCARD/")
    else:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = parent / candidate
    try:
        resolved = candidate.resolve(strict=False)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise _InspectionError("DISC_PATH_OUTSIDE_CARD") from error
    return resolved, relative


def _regular(root: Path, path: Path) -> bool:
    try:
        fd = _open_regular(root, path)
        try:
            return os.fstat(fd).st_size > 0
        finally:
            os.close(fd)
    except (OSError, _InspectionError):
        return False


def _cue_status(root: Path, cue: Path) -> tuple[bool, list[dict], list[str]]:
    files, warnings = [], []
    try:
        text = _read_text(root, cue)
        for line in text.splitlines():
            if not re.match(r"^\s*FILE(?:\s|$)", line, re.IGNORECASE):
                continue
            match = re.fullmatch(r'\s*FILE\s+(?:"([^"\r\n]+)"|(\S+))\s+\S+\s*', line, re.IGNORECASE)
            if not match:
                warnings.append("MALFORMED_CUE_FILE")
                continue
            if len(files) >= MAX_PLAYLIST_ENTRIES:
                warnings.append("DISC_REFERENCE_LIMIT")
                break
            try:
                track, relative = _path(root, cue.parent, match.group(1) or match.group(2))
                files.append({"relative_path": relative, "available": _regular(root, track)})
            except _InspectionError as error:
                warnings.append(str(error))
        if not files:
            warnings.append("CUE_HAS_NO_TRACK_FILES")
        if any(not entry["available"] for entry in files):
            warnings.append("MISSING_TRACK_FILE")
    except (OSError, UnicodeError, _InspectionError):
        warnings.append("CUE_UNREADABLE")
    return not warnings, files, list(dict.fromkeys(warnings))


def inspect_disc_set(root: Path, rom: Path, system_id: str) -> dict:
    """Describe existing references without changing launchability or any file."""
    result = {"kind": "none", "discs": [], "warnings": [], "disc_count": 0, "missing_count": 0}
    if system_id.upper() not in PS1_SYSTEMS:
        return result
    root = Path(root).resolve(strict=True)
    try:
        rom, relative = _path(root, root, str(rom))
    except _InspectionError as error:
        result["warnings"] = [str(error)]
        return result
    extension = rom.suffix.casefold()
    result["kind"] = "playlist" if extension == ".m3u" else ("native_container" if extension == ".pbp" else "single_disc")
    references = []
    if extension == ".m3u":
        try:
            text = _read_text(root, rom)
            for line in text.splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if len(references) >= MAX_PLAYLIST_ENTRIES:
                    result["warnings"].append("DISC_REFERENCE_LIMIT")
                    break
                references.append(raw)
            if not references:
                result["warnings"].append("EMPTY_PLAYLIST")
        except (OSError, UnicodeError, _InspectionError):
            result["warnings"].append("PLAYLIST_UNREADABLE")
    else:
        references = [str(rom)]
    for number, raw in enumerate(references, 1):
        entry = {"number": number, "label": Path(raw.replace("\\", "/")).name[:256],
                 "relative_path": "", "available": False, "warnings": []}
        try:
            path, disc_relative = _path(root, rom.parent, raw)
            entry["relative_path"] = disc_relative
            entry["available"] = _regular(root, path)
            if path.suffix.casefold() not in DISC_EXTENSIONS:
                entry["available"] = False
                entry["warnings"].append("UNSUPPORTED_DISC_REFERENCE")
            elif not entry["available"]:
                entry["warnings"].append("MISSING_DISC_FILE")
            elif path.suffix.casefold() == ".cue":
                available, files, warnings = _cue_status(root, path)
                entry.update(available=available, referenced_files=files, warnings=warnings)
        except _InspectionError as error:
            entry["warnings"].append(str(error))
        result["discs"].append(entry)
        result["warnings"].extend(entry["warnings"])
    result["disc_count"] = len(result["discs"]) if result["kind"] != "native_container" else None
    result["missing_count"] = sum(not entry["available"] for entry in result["discs"])
    if result["missing_count"]:
        result["warnings"].append("DISC_SET_REQUIRES_REVIEW")
    if result["kind"] == "native_container":
        result["description"] = "PBP disc count and switching are shown by the existing emulator's native menu."
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result
