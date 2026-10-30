#!/usr/bin/env python3
"""Package the Windows setup tools; never include a base OS or private data."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
STAMP = (2026, 10, 30, 0, 0, 0)

README = """SMART PRO - CUSTOM RETROPASS PSP PROJECT

Extract this ZIP on your Windows laptop, then double-click SETUP.cmd.

1. Back up the current card. This needs the microSD mounted in Windows.
   Your handheld is stuck in PPSSPP, so a microSD reader is the dependable
   route. USB works only if its existing USB Storage mode can be activated.
   Cancel any Windows format prompt. Never format the only games card.
2. Inspect recovery settings. This only reads known PPSSPP/startup files and
   produces a local report; it does not guess which configuration to reset.
3. Prepare the base and game files on the LAPTOP. This can download/check the
   pinned spruce archive before your reader arrives. Extraction needs 7-Zip.
   Read INSTALL-PREPARATION.txt for the exact options and requirements.

GAMES-AND-SAVES.txt explains game formats and why saves need separate review.
Keep the full verified backup, including hidden files and all configuration.
Do not upload backups, full manifests, ROMs, saves or private internal archives.

The optional device information app is in Optional-device-check. Use its guide
only after the backup succeeds and the original menu is accessible again.

This is preparation software, NOT a bootable SD-card image. The custom interface
has passed host checks. It still needs the actual firmware/card baseline and
physical testing of boot, controls, game launch/return and save preservation.
The private custom-source candidate is prepared separately; no download in this
kit claims to activate or hardware-qualify it. Do not install ordinary CrossMix
as a substitute for our project. The repository name is historical.

No tools upload your card data. A spare name-brand card is recommended for the
first device tests; a reader provides recovery if the handheld cannot boot.
"""


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output already exists")
    files = {}
    windows_names = (
        "SETUP.cmd", "START-HERE.cmd", "PREPARE-INSTALL.cmd", "INSPECT-RECOVERY.cmd",
        "TrimUI-Card-Helper.ps1", "Prepare-Install.ps1", "Inspect-Recovery.ps1",
        "README.txt", "GAMES-AND-SAVES.txt", "INSTALL-PREPARATION.txt",
        "tests/Test-Card-Helper.ps1", "tests/Test-Install-Preparation.ps1",
        "tests/Test-Recovery-Inspection.ps1",
    )
    for name in windows_names:
        files[name] = (PROJECT / "windows" / name).read_bytes()
    for name in ("config.json", "launch.sh", "collect.sh", "icon.png", "README.txt", "LICENSE"):
        relative = "Apps/SmartProCheck/" + name
        files["Optional-device-check/" + relative] = (PROJECT / "device-preflight" / relative).read_bytes()
    for name in ("windows-device-pilot.md", "ppsspp-card-recovery.md"):
        files["Guides/" + name] = (PROJECT / "docs" / name).read_bytes()
    files["Optional-device-check/DEVICE-STEPS.md"] = (PROJECT / "docs/windows-device-pilot.md").read_bytes()
    files["LICENSE"] = (PROJECT / "LICENSE").read_bytes()
    files["READ-FIRST.txt"] = README.encode()
    required = {"SETUP.cmd", "PREPARE-INSTALL.cmd", "INSPECT-RECOVERY.cmd", "START-HERE.cmd",
                "Prepare-Install.ps1", "Inspect-Recovery.ps1", "TrimUI-Card-Helper.ps1", "INSTALL-PREPARATION.txt"}
    if not required <= files.keys():
        raise ValueError("missing required tools: " + repr(sorted(required - files.keys())))
    manifest = {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in sorted(files.items())}
    files["kit-manifest.json"] = (json.dumps({"schema": 1, "kind": "windows-preparation-tools",
                                             "device_activated": False, "files": manifest}, indent=2) + "\n").encode()
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo("SmartPro-Setup/" + name, STAMP)
            entry.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("archive CRC failed")
        for name, data in files.items():
            if archive.read("SmartPro-Setup/" + name) != data:
                raise ValueError("archive readback mismatch")
    return {"path": str(output), "files": len(files), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "readback_verified": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
