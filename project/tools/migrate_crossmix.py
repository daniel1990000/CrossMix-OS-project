#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline migration preview/copy from CrossMix copies into a spruce spare card.

Only explicitly mapped favorites/history and owner-selected compatible battery
saves are eligible. No state conversion, source modification or emulator launch.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "packaging"))
from overlay import (OverlayError, atomic_write, canonical, digest,
                     ensure_no_links, identifier, locked, managed_root, no_duplicates, read_json, read_record, write_record, MAX_MANIFEST)

MAX_DATA = 16 * 1024 * 1024
MAX_ROWS = 20000
BATTERY_EXTENSIONS = {".srm", ".sav", ".sra", ".eep", ".fla", ".mcr", ".mcd", ".dsv"}
LISTS = {"favorites": ("Roms/favourite2.json", "Saves/pyui-favorites.json"),
         "history": ("Roms/recentlist.json", "Saves/pyui-recents.json")}
PYUI_KEYS = {"rom_file_path", "game_system_name", "display_name"}


def require(condition, message):
    if not condition:
        raise OverlayError(message)


def relative(value):
    require(isinstance(value, str) and value and len(value) <= 2048 and "\x00" not in value,
            "invalid migration path")
    require(not value.startswith("/") and "\\" not in value, "relative portable migration path required")
    require(all(part and part not in {".", ".."} for part in value.split("/")), "migration traversal rejected")
    return value


def contained(root, value):
    value = relative(value)
    root = ensure_no_links(Path(root))
    path = root / value
    ensure_no_links(path.parent)
    require(not path.is_symlink(), "migration symlink rejected")
    return path


def bounded(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_DATA,
            "migration input must be a bounded regular file")
    with open(path, "rb") as handle:
        data = handle.read(MAX_DATA + 1)
    require(len(data) <= MAX_DATA, "migration input exceeds limit")
    return data


def maybe_hash(path):
    return digest(bounded(path)) if path.exists() else None


def parse_legacy(raw):
    text = raw.decode("utf-8")
    if not text.strip():
        return []
    if text.lstrip().startswith("["):
        value = json.loads(text, object_pairs_hook=no_duplicates)
    else:
        value = [json.loads(line, object_pairs_hook=no_duplicates) for line in text.splitlines() if line.strip()]
    require(isinstance(value, list) and len(value) <= MAX_ROWS and all(isinstance(x, dict) for x in value),
            "legacy list must contain bounded object records")
    return value


def parse_pyui(raw):
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    require(isinstance(value, list) and len(value) <= MAX_ROWS, "PyUI list must be a bounded array")
    for record in value:
        require(isinstance(record, dict) and set(record) <= PYUI_KEYS and
                {"rom_file_path", "game_system_name"} <= set(record) and
                all(isinstance(x, str) for x in record.values()), "target PyUI entry has unknown/invalid fields; review it manually")
        require(record["rom_file_path"].startswith("/mnt/SDCARD/Roms/"), "PyUI ROM path outside Roms")
        relative(record["rom_file_path"][len("/mnt/SDCARD/"):])
        identifier(record["game_system_name"], "PyUI system name")
    return value


def source_rom_relative(root, value):
    require(isinstance(value, str), "legacy rompath missing")
    if value.startswith("/mnt/SDCARD/"):
        value = value[len("/mnt/SDCARD/"):]
    elif value.startswith(str(root) + "/"):
        value = value[len(str(root)) + 1:]
    relative(value)
    require(value.startswith("Roms/") and len(value.split("/")) >= 3, "legacy rompath is not a ROM entry")
    return value


def preview(crossmix, spruce, selection, output):
    source = ensure_no_links(Path(crossmix))
    target = ensure_no_links(Path(spruce))
    require(source.is_dir() and target.is_dir() and source != target and
            source not in target.parents and target not in source.parents, "use independent source and destination copies")
    systems = selection.get("systems", {})
    require(isinstance(systems, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in systems.items()),
            "explicit system mapping object required")
    for old, new in systems.items():
        identifier(old, "source system")
        identifier(new, "destination system")
    operations, review, provenance = [], [], []
    for label, (src_name, dst_name) in LISTS.items():
        src_path, dst_path = contained(source, src_name), contained(target, dst_name)
        if not src_path.exists():
            review.append({"kind": label, "reason": "legacy list absent"})
            continue
        raw = bounded(src_path)
        try:
            legacy = parse_legacy(raw)
            existing_raw = bounded(dst_path) if dst_path.exists() else b"[]\n"
            existing = parse_pyui(existing_raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            review.append({"kind": label, "reason": "list format requires manual review: " + str(exc)})
            continue
        merged = list(existing)
        seen = {(x["rom_file_path"], x["game_system_name"]) for x in existing}
        added = 0
        for index, record in enumerate(legacy):
            provenance.append({"kind": label, "index": index, "original_record": record})
            try:
                path = source_rom_relative(source, record.get("rompath"))
                parts = path.split("/")
                old = parts[1]
                require(old in systems, "system has no owner-approved mapping")
                new = systems[old]
                require(contained(target, "Emu/" + new + "/config.json").is_file(), "target system descriptor missing")
                target_relative = "Roms/" + new + "/" + "/".join(parts[2:])
                source_file, target_file = contained(source, path), contained(target, target_relative)
                require(source_file.is_file() and target_file.is_file(), "corresponding source/target ROM missing")
                # ROM contents are never read: copy selection establishes names, not identity.
                result = {"rom_file_path": "/mnt/SDCARD/" + target_relative, "game_system_name": new}
                if isinstance(record.get("label"), str) and record["label"]:
                    result["display_name"] = record["label"]
                key = (result["rom_file_path"], result["game_system_name"])
                if key in seen:
                    review.append({"kind": label, "index": index, "reason": "already present; existing metadata preserved"})
                    continue
                seen.add(key)
                merged.append(result)
                added += 1
            except (OverlayError, OSError) as exc:
                review.append({"kind": label, "index": index, "reason": str(exc)})
        if added:
            content = (json.dumps(merged, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
            operations.append({"kind": label, "source": src_name, "source_sha256": digest(raw),
                               "destination": dst_name, "before_sha256": maybe_hash(dst_path),
                               "after_sha256": digest(content), "content_base64": base64.b64encode(content).decode("ascii")})
    saves = selection.get("battery_saves", [])
    require(isinstance(saves, list) and len(saves) <= 512, "invalid battery save selection")
    for index, item in enumerate(saves):
        try:
            require(isinstance(item, dict), "battery save selection must be an object")
            src_name, dst_name = relative(item.get("source")), relative(item.get("destination"))
            require(Path(src_name).suffix.casefold() in BATTERY_EXTENSIONS and
                    Path(dst_name).suffix.casefold() in BATTERY_EXTENSIONS, "save states/unknown save formats are excluded")
            require(dst_name.startswith("Saves/saves/"), "battery saves must target confirmed spruce Saves/saves core folders")
            approval = item.get("compatibility", {})
            require(isinstance(approval, dict) and approval.get("reviewed") is True and
                    approval.get("kind") == "battery-save" and isinstance(approval.get("evidence"), str) and
                    approval["evidence"].strip(), "owner compatibility evidence required")
            src_path, dst_path = contained(source, src_name), contained(target, dst_name)
            data = bounded(src_path)
            after, before = digest(data), maybe_hash(dst_path)
            if before == after:
                review.append({"kind": "battery-save", "index": index, "reason": "identical destination already exists"})
                continue
            require(before is None or item.get("replace_existing") is True,
                    "destination differs; explicit replace_existing approval required")
            operations.append({"kind": "battery-save", "source": src_name, "source_sha256": after,
                               "destination": dst_name, "before_sha256": before, "after_sha256": after,
                               "compatibility": approval})
        except (OverlayError, OSError) as exc:
            review.append({"kind": "battery-save", "index": index, "reason": str(exc)})
    keys = [x["destination"].casefold() for x in operations]
    require(len(keys) == len(set(keys)), "duplicate/case-colliding migration destinations")
    plan = {"schema": 1, "kind": "crossmix-to-spruce-offline-preview", "source_root": str(source),
            "target_root": str(target), "operations": operations, "review": review,
            "provenance": provenance, "state_conversion": False,
            "rom_identity_note": "No ROM contents were read; owner must confirm identical games before save import."}
    output = Path(output).absolute()
    require(source not in output.parents and target not in output.parents, "preview output must be outside both cards")
    require(not output.exists(), "preview already exists")
    require(len(canonical(plan)) + 100 <= MAX_MANIFEST, "migration preview exceeds bounded journal size; split the selection")
    write_record(output, plan)
    return plan


def validate_operation(item):
    require(isinstance(item, dict) and item.get("kind") in {"favorites", "history", "battery-save"}, "invalid migration operation")
    relative(item.get("source"))
    name = relative(item.get("destination"))
    if item["kind"] == "battery-save":
        require(name.startswith("Saves/saves/") and Path(name).suffix.casefold() in BATTERY_EXTENSIONS,
                "invalid battery destination")
        require(Path(item["source"]).suffix.casefold() in BATTERY_EXTENSIONS, "save states cannot become battery saves")
        require(item.get("compatibility", {}).get("reviewed") is True and
                item["compatibility"].get("kind") == "battery-save", "compatibility approval missing")
    else:
        require(name == LISTS[item["kind"]][1] and item["source"] == LISTS[item["kind"]][0], "invalid list destination")
    for key in ("source_sha256", "after_sha256"):
        require(isinstance(item.get(key), str) and len(item[key]) == 64 and all(c in "0123456789abcdef" for c in item[key]),
                "invalid migration content hash")
    require(item.get("before_sha256") is None or (isinstance(item["before_sha256"], str) and len(item["before_sha256"]) == 64),
            "invalid migration precondition")


def apply(plan_path, transaction_id):
    identifier(transaction_id, "transaction id")
    plan = read_record(Path(plan_path))
    require(plan.get("schema") == 1 and plan.get("kind") == "crossmix-to-spruce-offline-preview", "invalid migration plan")
    source, target = ensure_no_links(Path(plan["source_root"])), ensure_no_links(Path(plan["target_root"]))
    require(source != target and source not in target.parents and target not in source.parents, "source/target overlap")
    operations = plan.get("operations")
    require(isinstance(operations, list) and 0 < len(operations) <= 514, "no eligible/bounded migration operations")
    prepared, destinations = [], set()
    for item in operations:
        validate_operation(item)
        require(item["destination"].casefold() not in destinations, "duplicate migration destination")
        destinations.add(item["destination"].casefold())
        src, dst = contained(source, item["source"]), contained(target, item["destination"])
        raw = bounded(src)
        require(digest(raw) == item["source_sha256"], "source changed since preview")
        require(maybe_hash(dst) == item["before_sha256"], "destination changed since preview")
        data = raw if item["kind"] == "battery-save" else base64.b64decode(item.get("content_base64", ""), validate=True)
        require(len(data) <= MAX_DATA and digest(data) == item["after_sha256"], "planned content hash mismatch")
        if item["kind"] != "battery-save":
            parse_pyui(data)
        prepared.append((item, data))
    root = managed_root(target, create=True)
    with locked(root):
        return _commit_migration(root, target, plan, prepared, transaction_id)


def _commit_migration(root, target, plan, prepared, transaction_id):
    for item, _ in prepared:
        require(maybe_hash(contained(target, item["destination"])) == item["before_sha256"],
                "destination changed while acquiring migration lock")
    transaction = root / "state" / "migrations" / transaction_id
    ensure_no_links(transaction)
    require(not transaction.exists(), "migration transaction already exists")
    transaction.mkdir(parents=True)
    journal = {"schema": 1, "kind": "migration-journal", "target_root": str(target), "status": "prepared",
               "operations": [], "provenance": plan.get("provenance", [])}
    for index, (item, _) in enumerate(prepared):
        dst = contained(target, item["destination"])
        backup_name = str(index) + ".backup"
        if dst.exists():
            atomic_write(transaction / backup_name, bounded(dst))
        record = {key: item[key] for key in ("destination", "before_sha256", "after_sha256")}
        record["backup"] = backup_name if dst.exists() else None
        journal["operations"].append(record)
    write_record(transaction / "journal.json", journal)
    for item, data in prepared:
        dst = contained(target, item["destination"])
        require(maybe_hash(dst) == item["before_sha256"], "destination changed during migration; use undo to recover")
        dst.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(dst, data)
    journal["status"] = "committed"
    write_record(transaction / "journal.json", journal)
    return {"transaction": str(transaction), "written": len(prepared), "source_modified": False}


def _undo(transaction):
    transaction = ensure_no_links(Path(transaction))
    journal = read_record(transaction / "journal.json")
    require(journal.get("schema") == 1 and journal.get("kind") == "migration-journal", "invalid undo journal")
    require(journal.get("status") in {"prepared", "committed"}, "transaction is already undone or invalid")
    target = ensure_no_links(Path(journal["target_root"]))
    expected_parent = managed_root(target) / "state" / "migrations"
    require(transaction.parent == expected_parent, "undo transaction is outside its project-owned directory")
    restore = []
    for item in journal["operations"]:
        dst = contained(target, item["destination"])
        require(item["destination"] in {x[1] for x in LISTS.values()} or item["destination"].startswith("Saves/saves/"),
                "undo destination out of scope")
        current = maybe_hash(dst)
        require(current in {item["before_sha256"], item["after_sha256"]}, "newer/different destination blocks undo")
        if current == item["before_sha256"]:
            continue  # also recovers a power interruption before this operation
        data = None
        if item["backup"] is not None:
            backup = contained(transaction, item["backup"])
            data = bounded(backup)
            require(digest(data) == item["before_sha256"], "undo backup hash mismatch")
        else:
            require(item["before_sha256"] is None, "undo backup missing")
        restore.append((dst, data))
    for dst, data in reversed(restore):
        if data is None:
            dst.unlink()
        else:
            atomic_write(dst, data)
    journal["status"] = "undone"
    write_record(transaction / "journal.json", journal)
    return {"restored": len(restore), "source_modified": False}


def undo(transaction):
    transaction = ensure_no_links(Path(transaction))
    journal = read_record(transaction / "journal.json")
    target = ensure_no_links(Path(journal["target_root"]))
    root = managed_root(target)
    require(transaction.parent == root / "state" / "migrations", "undo transaction is outside project-owned state")
    with locked(root):
        return _undo(transaction)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preview")
    for name in ("crossmix", "spruce", "selection", "output"):
        p.add_argument("--" + name, required=True)
    p = sub.add_parser("apply")
    p.add_argument("--plan", required=True)
    p.add_argument("--transaction", required=True)
    p = sub.add_parser("undo")
    p.add_argument("--transaction", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "preview":
            result = preview(args.crossmix, args.spruce, read_json(args.selection), args.output)
        elif args.command == "apply":
            result = apply(args.plan, args.transaction)
        else:
            result = undo(args.transaction)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except (OSError, OverlayError, ValueError, KeyError, UnicodeError) as exc:
        print("migration: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
