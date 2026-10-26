#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Name existing offline backups; restore only into a new expendable directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psp_shell.backup_catalog import BackupCatalog, BackupCatalogError
from psp_shell.recovery import BackupHistoryAdapter
from psp_shell.settings import SettingsError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path, help="External project-owned catalog JSON, outside inspected card and payloads")
    parser.add_argument("--inspected-card", action="append", default=[], type=Path, help="Refuse catalog metadata within this read-only source root")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Verify and register an existing payload; never copy active saves")
    register.add_argument("--payload", required=True, type=Path)
    register.add_argument("--label", required=True)
    register.add_argument("--note", default="")
    commands.add_parser("list", help="List historical checks; does not re-read payload bytes")
    detail = commands.add_parser("detail")
    detail.add_argument("entry_id")
    rename = commands.add_parser("rename")
    rename.add_argument("entry_id")
    rename.add_argument("--label", required=True)
    rename.add_argument("--note")
    rename.add_argument("--generation", required=True, type=int)
    remove = commands.add_parser("remove", help="Remove catalog entry only; never delete a backup")
    remove.add_argument("entry_id")
    remove.add_argument("--generation", required=True, type=int)
    check = commands.add_parser("verify", help="Fresh read-only byte verification with a catalog receipt")
    check.add_argument("entry_id")
    restore = commands.add_parser("restore", help="Rehearse restoration into a NEW expendable directory only")
    restore.add_argument("entry_id")
    restore.add_argument("--output", required=True, type=Path)
    commands.add_parser("recover", help="Recover an interrupted catalog metadata transaction")
    args = parser.parse_args(argv)
    adapter = None
    try:
        catalog = BackupCatalog(args.catalog, forbidden_roots=args.inspected_card)
        if args.command == "register":
            result = catalog.register(args.payload, args.label, note=args.note)
        elif args.command == "rename":
            result = catalog.rename(args.entry_id, args.label, args.generation, args.note)
        elif args.command == "remove":
            result = catalog.remove(args.entry_id, args.generation)
        elif args.command == "restore":
            result = catalog.restore(args.entry_id, args.output)
        elif args.command == "recover":
            result = {"generation": catalog.recover()["generation"], "recovered": True}
        else:
            adapter = BackupHistoryAdapter(args.catalog, forbidden_roots=args.inspected_card)
            if args.command == "list":
                result = adapter.history()
            elif args.command == "detail":
                result = adapter.detail(args.entry_id)
            else:
                generation = catalog.entry(args.entry_id)[1]
                result = adapter.verify(args.entry_id, generation)
                while result["state"] == "running":
                    adapter._thread.join(0.1)
                    result = adapter.job(result["job_id"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if args.command != "verify" or result["state"] == "verified" else 2
    except (BackupCatalogError, SettingsError, OSError, ValueError) as error:
        print("backup catalog: " + str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("backup catalog: verification interrupted; no new success is inferred", file=sys.stderr)
        return 130
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
