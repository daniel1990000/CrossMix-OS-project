#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare host-preview files with explicit original and RetroPass source scopes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "packaging"))
from overlay import ensure_no_links, OverlayError, SPRUCE_COMMIT, PYUI_TREE, relative_path
from release_descriptor import original_source_scope, original_source_file, PAYLOAD_TOOLS, validate_retropass_vendor


def build_payload(project, output, source_lock=None, *, source_inventory=None):
    project = ensure_no_links(Path(project))
    output = ensure_no_links(Path(output))
    if output.exists():
        raise OverlayError("payload output must be a new directory")
    if project == output or output in project.parents or project in output.parents:
        raise OverlayError("payload must be outside the source project")
    if not (project / "psp_shell/__main__.py").is_file():
        raise OverlayError("original psp_shell source entrypoint missing")
    sources = []
    for folder, destination, extensions in (("psp_shell", "app/psp_shell", {".py"}),
                                            ("retropass", "app/retropass", {".py", ".txt", ".json"}),
                                            ("bridge", "app/bridge", {".py"}),
                                            ("profiles", "app/profiles", {".json"}),
                                            ("ppsspp/theme", "app/ppsspp/theme", {".ini", ".json", ".md", ".svg", ""}),
                                            ("assets", "assets", {".ttf", ".txt", ".png", ".svg", ".wav"})):
        root = project / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(project)
            if not original_source_scope(relative):
                continue
            if path.is_symlink():
                raise OverlayError("source symlinks are excluded from a payload")
            if not path.is_file() or path.suffix.casefold() not in extensions or "__pycache__" in path.parts:
                continue
            name = destination + "/" + path.relative_to(root).as_posix()
            if not original_source_file(relative):
                raise OverlayError("payload input is outside the original source allowlist")
            relative_path(name)
            sources.append((path, name))
    # The backup screen reuses the existing fresh readback implementation.
    # Keep this narrow: no arbitrary tool, command or auto-restore endpoint.
    for name in PAYLOAD_TOOLS:
        path = project / "tools" / name
        if path.is_symlink() or not path.is_file():
            raise OverlayError("existing recovery verifier source missing")
        sources.append((path, "app/tools/" + name))
    has_retropass = (project / "retropass/source-lock.json").is_file()
    if has_retropass:
        validate_retropass_vendor(project)
        for path in sorted((project / "vendor/retropass").rglob("*")):
            if path.is_symlink():
                raise OverlayError("RetroPass source symlinks are excluded")
            if path.is_file():
                sources.append((path, "notices/RetroPass-source/" +
                                path.relative_to(project / "vendor/retropass").as_posix()))
    output.mkdir(parents=True)
    try:
        consumed, copies = {}, []

        def captured_bytes(path):
            relative = path.relative_to(project).as_posix()
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if source_inventory is not None and source_inventory.get(relative) != digest:
                raise OverlayError("payload input differs from captured source inventory: " + relative)
            consumed[relative] = digest
            return data

        def copy_source(path, destination):
            data = captured_bytes(path)
            destination.write_bytes(data)
            destination.chmod(0o644)
            copies.append({"source_path": path.relative_to(project).as_posix(),
                           "payload_path": destination.relative_to(output).as_posix(),
                           "sha256": hashlib.sha256(data).hexdigest()})

        for path, name in sources:
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_source(path, destination)
        metadata, notices = output / "metadata", output / "notices"
        metadata.mkdir(exist_ok=True)
        notices.mkdir(exist_ok=True)
        lock = {"schema": 1, "base_commit": SPRUCE_COMMIT, "pyui_git_tree": PYUI_TREE,
                "kind": "retropass-host-preview" if has_retropass else "original-host-preview", "hardware_qualified": False,
                "upstream_source_bundled": has_retropass, "firmware_emulators_roms_bundled": False}
        if source_lock:
            lock_path = Path(source_lock)
            provenance = json.loads(captured_bytes(lock_path) if source_inventory is not None else lock_path.read_bytes())
            if provenance.get("base", {}).get("source_commit") != SPRUCE_COMMIT:
                raise OverlayError("source lock is not the selected spruce baseline")
            lock["source_lock"] = provenance
        (metadata / "source-provenance.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if (project / "LICENSE").is_file():
            copy_source(project / "LICENSE", notices / "ORIGINAL-PROJECT-LICENSE.txt")
        else:
            raise OverlayError("project/LICENSE is required to package original source")
        font_notice = project / "assets/fonts/OFL.txt"
        if not font_notice.is_file():
            raise OverlayError("font license notice missing")
        copy_source(font_notice, notices / "NotoSans-OFL.txt")
        if has_retropass:
            copy_source(project / "retropass/NOTICE.txt", notices / "RetroPass-NOTICE.txt")
            copy_source(project / "vendor/retropass/LICENSE.txt", notices / "RetroPass-GPL-2.0.txt")
            lock["retropass"] = json.loads(captured_bytes(project / "retropass/source-lock.json"))
            lock["licence_scopes"] = {"retropass": "GPL-2.0-only", "original_helpers": "MIT", "NotoSans": "OFL-1.1"}
            (metadata / "source-provenance.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (notices / "DEPENDENCIES.txt").write_text(
            ("This package contains original project helpers, Noto Sans, and GPL-2.0-only RetroPass adaptations.\n"
             "Complete pinned RetroPass source is retained in notices/RetroPass-source; translated runtime source is in app/retropass.\n"
             "The project MIT notice does not relicense the RetroPass source or adaptations.\n" if has_retropass else
             "This package contains original project Python code and original assets, plus the licensed Noto Sans font.\n") +
            "It does not contain spruceOS/PyUI source, SDL, Python, PySDL2, Pillow, firmware, emulators, ROMs, saves or signing keys.\n"
            "The desktop preview requires installed Python >=3.9, PySDL2 0.9.17, Pillow 11.1.0 and system SDL2.\n"
            "Reusing a device's spruce/PyUI runtime requires the separate source-use/runtime/hardware gates.\n"
            "spruceOS and PyUI retain their separate noncommercial/notification terms; no compatibility or permission is implied.\n",
            encoding="utf-8")
        entries = []
        for path in sorted(output.rglob("*")):
            if path.is_file():
                entries.append({"path": path.relative_to(output).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        (metadata / "original-payload.json").write_text(json.dumps({
            "schema": 1, "files": entries, "source_payload": copies,
            "source_files": [{"path": name, "sha256": digest} for name, digest in sorted(consumed.items())],
            "source_inventory_verified": source_inventory is not None}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"payload": str(output), "files": len(entries) + 1, "device_qualified": False}
    except BaseException:
        shutil.rmtree(output)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).absolute().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-lock", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build_payload(args.project, args.output, args.source_lock), indent=2))
        return 0
    except (OSError, ValueError, OverlayError) as exc:
        print("payload: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
