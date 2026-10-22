#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded read-only evidence collector. Writes only the explicit output file.

Run with Python 3 on the original device, or inspect a mounted root with --root.
No legacy launcher, service, firmware, graphics or hardware-control command runs.
Unknown observations stay unknown; operator confirmations retain provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys

MAX_TEXT = 64 * 1024
MAX_ELF = 128 * 1024 * 1024
SECRET_WORDS = re.compile(r"(?i)(password|passwd|psk|token|secret|credential|authorization|private[_-]?key)")


def redact(text):
    """Remove secret assignments, addresses and user/home identities from exports."""
    if re.search(r"-----BEGIN .*PRIVATE KEY-----", text):
        return "[REDACTED PRIVATE KEY]"
    text = re.sub(r"(?im)^.*(?:password|passwd|psk|token|secret|credential|authorization|private[_-]?key).*$",
                  "[REDACTED FIELD]", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "[MAC]", text)
    text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", "[IP]", text)
    text = re.sub(r"(?i)(?<![\w])(?:[0-9a-f]{1,4}:){2,}[0-9a-f:]+(?:%\w+)?", "[IPv6]", text)
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"/(?:home|Users)/[^/\s]+", "/home/[USER]", text)
    text = re.sub(r"(?i)(?:ssid|hostname)\s*[:=]\s*[^\r\n]+", "identity=[REDACTED]", text)
    text = re.sub(r"(?im)^\s*(?:Serial|Serial Number)\s*[:=].*$", "Serial: [REDACTED]", text)
    return text


def bounded_read(path, limit=MAX_TEXT):
    try:
        # /proc and sysfs often report size zero, so bound the actual read too.
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            return None
        return data.decode("utf-8", errors="replace").replace("\x00", " ").strip()
    except (OSError, ValueError):
        return None


def safe_path(root, relative):
    path = root / relative.lstrip("/")
    # The caller provides a trusted, fixed path; nevertheless avoid mounted-root escapes.
    try:
        path.resolve().relative_to(root.resolve())
        return path
    except (ValueError, OSError, RuntimeError):
        return None


def read_at(root, relative):
    path = safe_path(root, relative)
    return bounded_read(path) if path else None


def hash_at(root, relative):
    path = safe_path(root, relative)
    if path is None:
        return None
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ELF:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        return {"path": relative, "size": info.st_size, "sha256": h.hexdigest()}
    except OSError:
        return None


def elf_at(root, relative):
    path = safe_path(root, relative)
    if path is None:
        return None
    result = hash_at(root, relative)
    if result is None:
        return None
    try:
        with open(path, "rb") as handle:
            header = handle.read(64)
        if len(header) < 20 or header[:4] != b"\x7fELF":
            return None
        byte_order = "little" if header[5] == 1 else "big"
        result.update({"class": {1: "ELF32", 2: "ELF64"}.get(header[4], "unknown"),
                       "machine": int.from_bytes(header[18:20], byte_order),
                       "endianness": byte_order})
        return result
    except OSError:
        return None


def collect(root=Path("/"), sd_root=Path("/mnt/SDCARD"), profile=None,
            confirm_model=None, confirm_firmware=None):
    root, sd_root = Path(root).absolute(), Path(sd_root).absolute()
    model_observations = {}
    for name in ("proc/device-tree/model", "proc/device-tree/compatible", "sys/firmware/devicetree/base/model", "proc/cpuinfo"):
        value = read_at(root, name)
        if value is not None:
            model_observations["/" + name] = redact(value)
    model_text = " ".join(model_observations.values()).casefold()
    model = None
    if ("tg5040" in model_text or "smart pro" in model_text) and "brick" not in model_text and not re.search(r"smart pro\s+s\b", model_text):
        model = "trimui-smart-pro"
    firmware_observations = {}
    for name in ("etc/version", "etc/trimui_version", "etc/firmware_version", "usr/trimui/etc/version.txt", "etc/os-release"):
        value = read_at(root, name)
        if value is not None:
            firmware_observations["/" + name] = redact(value)
    # Do not mistake a bundled/minimum firmware file for the installed version.
    firmware = None
    for path, text in firmware_observations.items():
        if path == "/etc/os-release":
            continue
        match = re.search(r"\b(1\.\d+\.\d+)\b", text)
        if match:
            firmware = match.group(1)
            break
    executables = []
    for name in ("usr/trimui/bin/MainUI", "usr/trimui/bin/hardwareservice", "usr/trimui/bin/keymon",
                 "usr/lib/libSDL2-2.0.so.0", "usr/lib/libEGL.so", "usr/lib/libGLESv2.so", "lib/libc.so.6"):
        result = elf_at(root, name)
        if result:
            executables.append(result)
    architecture = "aarch64" if any(x["machine"] == 183 for x in executables) else None
    if root == Path("/"):
        architecture = platform.machine()
        architecture = {"arm64": "aarch64", "AMD64": "x86_64"}.get(architecture, architecture)
    confirmations = {}
    for key, value in (("model", confirm_model), ("firmware", confirm_firmware)):
        if value:
            confirmations[key] = {"value": value, "provenance": "explicit operator assertion; compare observation evidence"}
    baseline, pyui_tree, baseline_evidence = None, None, []
    if profile is not None:
        contracts = profile.get("baseline_files", {})
        for name, expected in sorted(contracts.items()):
            if not isinstance(name, str) or name.startswith("/") or ".." in name.split("/"):
                raise ValueError("unsafe profile contract path")
            result = hash_at(sd_root, name)
            git_hash = None
            if result:
                path = safe_path(sd_root, name)
                h = hashlib.sha1()
                h.update(("blob " + str(path.stat().st_size) + "\0").encode("ascii"))
                with open(path, "rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        h.update(block)
                git_hash = h.hexdigest()
            actual = result["sha256"] if result and len(expected) == 64 else git_hash
            baseline_evidence.append({"path": name, "sha256": result["sha256"] if result else None,
                                      "git_blob": git_hash, "matches_profile": actual is not None and actual == expected})
        if contracts and all(x["matches_profile"] for x in baseline_evidence):
            baseline = profile.get("base_commit")
            pyui_tree = profile.get("pyui_git_tree")
    device = {"model": confirm_model or model, "firmware": confirm_firmware or firmware,
              "architecture": architecture, "base_commit": baseline, "pyui_git_tree": pyui_tree}
    mounts = []
    mount_text = read_at(root, "proc/mounts") or ""
    for line in mount_text.splitlines()[:128]:
        columns = line.split()
        if len(columns) >= 4:
            mounts.append({"mountpoint": redact(columns[1]), "filesystem": columns[2],
                           "flags": [x for x in columns[3].split(",") if x in {"ro", "rw", "noexec", "nosuid", "nodev", "sync"}]})
    processes = []
    proc = root / "proc"
    if proc.is_dir():
        for entry in sorted(proc.iterdir(), key=lambda x: x.name)[:4096]:
            if entry.name.isdigit():
                name = read_at(root, "proc/" + entry.name + "/comm")
                if name:
                    processes.append({"pid": int(entry.name), "name": redact(name[:96])})
    scripts = []
    for name in ("usr/trimui/bin/runtrimui.sh", "usr/trimui/bin/runtrimui-original.sh", "usr/trimui/bin/runtrimui", "etc/init.d/rcS", "bin/bash"):
        result = hash_at(root, name)
        if result:
            scripts.append(result)
    for name in (".tmp_update/updater", "spruce/scripts/runtime.sh", "spruce/scripts/principal.sh", "trimui/app/runtrimui.sh"):
        result = hash_at(sd_root, name)
        if result:
            scripts.append(result)
    endpoints = {}
    for group, parent, fields in (
        ("power", "sys/class/power_supply", ("type", "status", "capacity", "voltage_now")),
        ("thermal", "sys/class/thermal", ("type", "temp")),
        ("backlight", "sys/class/backlight", ("brightness", "max_brightness")),
    ):
        location = root / parent
        endpoints[group] = []
        if location.is_dir():
            for entry in sorted(location.iterdir())[:32]:
                row = {"endpoint": "/" + parent + "/" + entry.name}
                for field in fields:
                    value = read_at(root, parent + "/" + entry.name + "/" + field)
                    if value is not None:
                        row[field] = redact(value[:128])
                endpoints[group].append(row)
    capabilities = read_at(root, "proc/bus/input/devices")
    card_lists = {}
    for name in ("pyui-favorites.json", "pyui-recents.json", "gameswitcher.json", "pyui-apps.json", "pyui-state.json"):
        text = read_at(sd_root, "Saves/" + name)
        if text is None:
            card_lists[name] = {"present": False}
            continue
        try:
            value = json.loads(text)
            card_lists[name] = {"present": True, "valid_json": True, "type": type(value).__name__,
                                "count": len(value) if isinstance(value, (dict, list)) else None}
        except (ValueError, RecursionError):
            card_lists[name] = {"present": True, "valid_json": False}
    scene_hashes = []
    scene = root / "usr/trimui/scene"
    if scene.is_dir():
        for path in sorted(scene.iterdir())[:64]:
            if path.is_file() and not path.is_symlink():
                result = hash_at(root, path.relative_to(root).as_posix())
                if result:
                    scene_hashes.append(result)
    return {"schema": 1, "kind": "read-only-device-inventory", "device": device,
            "profile_id": profile.get("id") if profile else None,
            "source_profile_verified": bool(baseline),
            "source_identity_note": "Matches locked file contracts; not proof of every file in a release archive.",
            "operator_confirmations": confirmations, "model_observations": model_observations,
            "firmware_observations": firmware_observations, "kernel": redact(read_at(root, "proc/version") or "unobserved"),
            "mounts": mounts, "process_names_only": processes, "elf_identity": executables,
            "boot_and_launcher_hashes_only": scripts, "baseline_contracts": baseline_evidence,
            "internal_scene_hashes_only": scene_hashes, "frontend_lists_summary_only": card_lists,
            "input_capabilities": redact(capabilities) if capabilities else None,
            "audio_cards": redact(read_at(root, "proc/asound/cards") or "unobserved"),
            "endpoints": endpoints,
            "deferred_device_evidence": ["SDL video backend and EGL/GLES strings require the native graphics probe",
                                          "ELF interpreters, dynamic dependency closure and versioned symbols require the ABI probe",
                                          "input event assignments, suspend, USB and save integrity require physical tests"],
            "privacy": "No ROM/save content, process arguments/environment, Wi-Fi/service configuration, secrets, or raw boot scripts collected."}


def write_output(output, data, sd_root):
    output = Path(output).absolute()
    lowered = {x.casefold() for x in output.resolve().parts}
    if lowered & {"roms", "saves", "bios", "retroarch", "emus"}:
        raise ValueError("inventory output cannot be inside ROM/save/emulator/BIOS directories")
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists; choose a new filename")
    if not output.parent.is_dir():
        raise ValueError("output parent must already exist")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--sd-root", type=Path, default=Path("/mnt/SDCARD"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--confirm-model", choices=("trimui-smart-pro",))
    parser.add_argument("--confirm-firmware")
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text()) if args.profile else None
        report = collect(args.root, args.sd_root, profile, args.confirm_model, args.confirm_firmware)
        write_output(args.output, report, args.sd_root)
        print(str(args.output))
        return 0
    except (OSError, ValueError) as exc:
        print("inventory: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
