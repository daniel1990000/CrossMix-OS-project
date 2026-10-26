#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a verified, original-only development deliverable, never a device release.

The default signer is generated in scratch and deleted. Its public key is
labelled development-only. Signed reproducibility is checked with that same
key; use an explicit external fixed keypair to reproduce signatures across runs.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).absolute().parent
PROJECT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT / "tools"))
import overlay
from build_payload import build_payload
from fixture_card import create_fixture
from release_descriptor import (resolve as resolve_descriptor, original_source_scope, original_source_file,
                                source_inventory, SOURCE_FOLDERS, SOURCE_ROOT_FILES, SOURCE_EXTENSIONS)


def put_json(path, value):
    path.write_bytes(overlay.canonical(value) + b"\n")


def zip_files(path, entries, epoch):
    """Stable order, UTC DOS timestamp, regular 0644 modes, no host extra fields."""
    timestamp = datetime.datetime.fromtimestamp(max(epoch, 315532800), datetime.timezone.utc)
    timestamp = timestamp.replace(microsecond=0, second=timestamp.second // 2 * 2)
    stamp = (timestamp.year, timestamp.month, timestamp.day, timestamp.hour, timestamp.minute, timestamp.second)
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries):
            overlay.relative_path(name)
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def original_source_entries(project):
    entries = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if not original_source_scope(relative):
            continue
        if path.is_symlink():
            raise overlay.OverlayError("source archive refuses symlinks")
        if not path.is_file() or not original_source_file(relative):
            continue
        overlay.relative_path(relative.as_posix())
        overlay.require(path.stat().st_size <= overlay.MAX_FILE, "source artifact file too large")
        entries.append(("smartpro-original-source/" + relative.as_posix(), path.read_bytes()))
    overlay.require(any(name.endswith("/LICENSE") for name, _ in entries), "original source license missing")
    return entries


def materialize_source(entries, output):
    """Build only from the bytes already inventoried, never from the live tree."""
    output.mkdir(mode=0o700)
    seen = set()
    for name, data in entries:
        prefix = "smartpro-original-source/"
        overlay.require(name.startswith(prefix), "captured source path has no archive root")
        relative = name[len(prefix):]
        overlay.relative_path(relative)
        overlay.require(relative not in seen, "duplicate captured source path")
        overlay.require(original_source_file(relative) or relative == "metadata/spruce-source-lock.json",
                        "captured source path is outside the original allowlist")
        seen.add(relative)
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {item["path"]: item["sha256"] for item in source_inventory(entries)}


def host_smoke(python, release, scratch):
    environment = dict(os.environ)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(release / "app"),
                       SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    screenshot, report = scratch / "preview.png", scratch / "preview.json"
    command = [str(python), "-m", "psp_shell", "--demo", "--headless", "--frames", "3",
               "--screen", "settings", "--actions", "down,up,right,left", "--frame-time", "0",
               "--state-dir", str(scratch / "preview-state"), "--screenshot", str(screenshot),
               "--report", str(report)]
    result = subprocess.run(command, env=environment, cwd=release, capture_output=True, text=True, timeout=60)
    overlay.require(result.returncode == 0, "packaged host preview failed: " + result.stderr[-2000:])
    observed = json.loads(report.read_text(encoding="utf-8"))
    overlay.require(observed.get("frames", 0) >= 1 and observed.get("device_performance_claim") is False and
                    observed.get("real_game_launches") == 0, "preview did not report host-only rendering")
    overlay.require(screenshot.is_file() and screenshot.stat().st_size > 1000, "preview screenshot missing")
    # Exercise existing original dispatch contracts from the *installed* payload.
    probe = """
import json, subprocess, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
from psp_shell import build_info
from psp_shell.demo import DemoBackend
from psp_shell.settings import SettingsStore
from psp_shell.app import Dispatcher
from psp_shell.adapters.spruce import SpruceBackend
from psp_shell.recovery import BackupStatusAdapter, BackupHistoryAdapter
from psp_shell.backup_catalog import BackupCatalog
from tools.recovery_payload import backup
from tools.backup_catalog import main as catalog_command

expected = json.loads(Path('metadata/development-release.json').read_text())
assert build_info()['release_id'] == expected['release_id']
assert build_info()['source_kind'] == 'installed-package'
with tempfile.TemporaryDirectory(prefix='installed-preview-contract-') as temporary:
    root = Path(temporary)
    d = Dispatcher(DemoBackend(), SettingsStore(root/'preferences'), root/'reports')
    assert d.dispatch('settings.get')['generation'] >= 0
    g = d.dispatch('library.query', {'system_id':'PSP', 'search':'Skyline'})['items'][0]
    assert d.dispatch('game.info', {'game_id':g['game_id']})['game_id'] == g['game_id']
    assert all(x['system_id'] == 'PSP' for x in d.dispatch('library.recent', {'system_id':'PSP'}))
    card = root/'read-only-library'
    (card/'Emu/GB').mkdir(parents=True)
    (card/'Emu/GB/config.json').write_text(json.dumps({'label':'Game Boy', 'extlist':'gb',
        'default_emulator':'gambatte', 'devices':['TRIMUI_A133P']}))
    (card/'Roms/GB').mkdir(parents=True)
    records = []
    for index in range(75):
        name = 'Fixture%03d.gb' % index
        (card/'Roms/GB'/name).write_bytes(b'non-executable synthetic library fixture')
        records.append({'game_system_name':'GB', 'rom_file_path':'/mnt/SDCARD/Roms/GB/' + name})
    (card/'Collections').mkdir()
    (card/'Collections/collections.json').write_text(json.dumps([
        {'collection_name':'Installed collection', 'game_list':records}]))
    library_before = {p.relative_to(card).as_posix():p.read_bytes() for p in card.rglob('*') if p.is_file()}
    discovery = Dispatcher(SpruceBackend(card), SettingsStore(root/'library-preferences'), root/'library-reports')
    collection = discovery.dispatch('library.collections')[0]
    scope = {'source':'collection', 'collection_id':collection['id'], 'system_id':'GB',
             'search':'Fixture', 'sort':'title_asc', 'available_only':True}
    page = discovery.dispatch('library.query', {**scope, 'offset':0, 'limit':40})
    assert page['total'] == 75 and len(page['items']) == 40
    with patch('psp_shell.adapters.spruce.secrets.choice', side_effect=lambda rows:rows[-1]):
        chosen = discovery.dispatch('library.random', scope)
    assert chosen['label'] == 'Fixture074' and chosen['game_id'] not in {row['game_id'] for row in page['items']}
    assert not discovery.backend._actions
    assert library_before == {p.relative_to(card).as_posix():p.read_bytes() for p in card.rglob('*') if p.is_file()}
    assert d.dispatch('backup.status')['status'] == 'unavailable'
    src = root/'stopped-saves'
    src.mkdir(mode=0o700)
    (src/'fixture.sav').write_bytes(b'original')
    backup(src, root/'backup', 'saves')
    d.backup_adapter = BackupStatusAdapter({'saves':root/'backup'})
    assert d.dispatch('backup.status')['status'] == 'verified'
    (root/'backup/data/fixture.sav').write_bytes(b'changed')
    assert d.dispatch('backup.status')['status'] == 'unavailable'
    (root/'backup/data/fixture.sav').write_bytes(b'original')
    catalog = root/'backups.json'
    registered = BackupCatalog(catalog).register(root/'backup', 'Installed smoke backup')
    adapter = BackupHistoryAdapter(catalog)
    d.backup_adapter = adapter
    try:
        history = d.dispatch('backup.history')
        assert history['entries'][0]['label'] == 'Installed smoke backup'
        job = d.dispatch('backup.verify', {'entry_id':registered['entry_id'],
                                          'expected_generation':history['generation']})
        deadline = time.monotonic() + 10
        while job['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.01)
            job = d.dispatch('backup.job', {'job_id':job['job_id']})
        assert job['state'] == 'verified'
        history = d.dispatch('backup.history')
        assert history['entries'][0]['status'] == 'previously_verified'
        detail = d.dispatch('backup.detail', {'entry_id':registered['entry_id']})
        assert detail['label'] == 'Installed smoke backup' and detail['physical_restore_tested'] is False
        job = d.dispatch('backup.verify', {'entry_id':registered['entry_id'],
                                          'expected_generation':history['generation']})
        job = d.dispatch('backup.cancel', {'job_id':job['job_id']})
        deadline = time.monotonic() + 10
        while job['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(0.01)
            job = d.dispatch('backup.job', {'job_id':job['job_id']})
        assert job['state'] in {'verified', 'cancelled'}
        assert catalog_command(['--catalog', str(catalog), 'list']) == 0
        rendered = 0
        for screen, arguments in [('help', ['--demo']),
                                  ('backups', ['--demo', '--backup-catalog', str(catalog)]),
                                  ('collections', ['--sd-root', str(card)])]:
            screenshot, report = root/(screen + '.png'), root/(screen + '.json')
            run = subprocess.run([sys.executable, '-m', 'psp_shell', *arguments, '--headless',
                '--frames', '2', '--screen', screen, '--state-dir', str(root/('state-' + screen)),
                '--screenshot', str(screenshot), '--report', str(report)], capture_output=True, text=True, timeout=20)
            assert run.returncode == 0, run.stderr
            observation = json.loads(report.read_text())
            assert observation['real_game_launches'] == 0 and observation['device_performance_claim'] is False
            assert observation['frames'] == 2 and screenshot.stat().st_size > 1000
            rendered += observation['frames']
        assert (root/'backup/data/fixture.sav').read_bytes() == b'original'
        r = d.dispatch('interface.switch', {'interface':'classic'})
        assert r['interface'] == 'classic' and r['state'] == 'releasing_ui'
    finally:
        adapter.close()
print(json.dumps({'settings':True, 'game_information':True, 'combined_filters':True,
                  'fresh_backup_readback':True, 'named_backup_history':True,
                  'installed_build_identity':True, 'classic_delegation_contract':True,
                  'discovery_scope':True, 'full_result_random':True, 'backup_cancel_dispatch':True,
                  'help_backups_collections_rendered_frames':rendered}))
"""
    contract = subprocess.run([str(python), "-c", probe], env=environment, cwd=release,
                              capture_output=True, text=True, timeout=90)
    overlay.require(contract.returncode == 0, "packaged settings/classic contract failed: " + contract.stderr[-2000:])
    contracts = json.loads(contract.stdout.splitlines()[-1])
    return {"rendered_frames": observed["frames"] + contracts["help_backups_collections_rendered_frames"],
            "navigation_actions_exercised": True,
            "settings_dispatch": True, "classic_delegation_contract": True, "clean_process_exit": True,
            "game_information": True, "combined_filters": True, "fresh_backup_readback": True,
            "named_backup_history": True, "installed_build_identity": True,
            "discovery_scope": True, "full_result_random": True, "backup_cancel_dispatch": True,
            "help_backups_collections_rendered": True,
            "physical_device_verified": False, "real_game_launches": 0}, screenshot


def build(project, output, release=None, epoch=None, *, source_lock=None, include_source=False,
          smoke_python=None, private_key=None, public_key=None, release_descriptor=None):
    project = overlay.ensure_no_links(Path(project))
    output = overlay.ensure_no_links(Path(output))
    overlay.require(output != project and project not in output.parents and output not in project.parents,
                    "artifact output must be outside project source")
    overlay.require(not output.exists(), "artifact output already exists")
    overlay.require(bool(private_key) == bool(public_key), "provide both external signing-key paths or neither")
    source_entries = original_source_entries(project)
    if source_lock:
        source_entries.append(("smartpro-original-source/metadata/spruce-source-lock.json",
                               Path(source_lock).read_bytes()))
    selection = snapshot = None
    if release_descriptor is not None:
        selection, snapshot = resolve_descriptor(project, release_descriptor, source_entries, source_lock)
        if release is None:
            release = selection["descriptor"]["release_id"]
        if epoch is None:
            epoch = selection["descriptor"]["source_date_epoch"]
        overlay.require(release == selection["descriptor"]["release_id"],
                        "--release differs from the current release descriptor")
    overlay.identifier(release, "development release id")
    overlay.require(type(epoch) is int and 315532800 <= epoch <= 4354819198,
                    "ZIP/release timestamp must be UTC 1980 through 2107")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = Path(tempfile.mkdtemp(prefix=".development-release-", dir=output.parent))
    try:
        with tempfile.TemporaryDirectory(prefix="smartpro-development-build-") as scratch_name:
            scratch = Path(scratch_name)
            card = scratch / "fixture-card"
            create_fixture(card)
            profile = overlay.read_json(card / "fixture-profile.json")
            inventory = overlay.read_json(card / "fixture-inventory.json")
            captured_project = scratch / "captured-source"
            captured_inventory = materialize_source(source_entries, captured_project)
            captured_lock = captured_project / "metadata/spruce-source-lock.json" if source_lock else None
            payload = scratch / "payload"
            build_payload(captured_project, payload, captured_lock, source_inventory=captured_inventory)
            generated_key = private_key is None
            if generated_key:
                key_dir = scratch / "keys"
                key_dir.mkdir()
                private_key, public_key = key_dir / "private", key_dir / "public"
                overlay.keygen(private_key, public_key)
            else:
                private_key, public_key = Path(private_key).absolute(), Path(public_key).absolute()
            public = overlay.load_key(public_key, 32)
            key_id = overlay.digest(public)
            put_json(payload / "metadata/development-release.json", {
                "schema": 1, "release_id": release, "status": "host-preview-only",
                "source_date_epoch": epoch, "base_commit": overlay.SPRUCE_COMMIT,
                "pyui_git_tree": overlay.PYUI_TREE, "device_activation_qualified": False,
                "trust": "development test signature; not upstream identity or production authorization",
                "release_selection": selection})
            # A single signing identity is used for both clean archive creations.
            archive_name = release + ".tar"
            archive = scratch / archive_name
            second = scratch / "rebuild.tar"
            for path in (archive, second):
                overlay.create_archive(payload, path, private_key, public_key, profile, release,
                                       "python-extension", source_date_epoch=epoch)
            overlay.require(archive.read_bytes() == second.read_bytes(), "signed overlay rebuild differs")
            with overlay.VerifiedArchive(archive, public) as verified:
                file_count = len(verified.manifest["files"])
            overlay.stage_archive(archive, public, card, profile, inventory, fixture=True)
            overlay.activate_release(card, release, public, profile, inventory, fixture=True)
            installed = overlay.managed_root(card) / "releases" / release
            smoke = {"executed": False, "reason": "no --smoke-python supplied", "physical_device_verified": False}
            if smoke_python:
                details, screenshot = host_smoke(Path(smoke_python).absolute(), installed, scratch)
                smoke = {"executed": True, **details}
                shutil.copyfile(screenshot, temporary_output / "host-preview.png")
                evidence = {"schema": 1, "release_id": release, "profile_id": profile["id"],
                            "manifest_sha256": overlay.file_digest(installed / "manifest.json"),
                            "checks": dict.fromkeys(("first_frame", "input", "settings", "classic_fallback", "clean_exit"), True),
                            "evidence_reference": "host-fixture renderer/navigation/settings/classic-delegation contracts; no physical device"}
                overlay.confirm_health(card, public, evidence)
            rolled_back = overlay.rollback(card, public)
            overlay.require(rolled_back["current_release"] is None and
                            (overlay.managed_root(card) / "state/force-classic").is_file(), "fixture rollback failed")
            shutil.copyfile(archive, temporary_output / archive_name)
            (temporary_output / "development-verification.pub").write_bytes(public)
            preview_instructions = (
                "HOST DEVELOPMENT PREVIEW ONLY. No original Smart Pro hardware is qualified.\n"
                "Extract this ZIP into a new directory on your computer. Do not copy it over a device card.\n"
                "Install Python >=3.9, system SDL2, PySDL2==0.9.17 and Pillow==11.1.0 in a virtual environment.\n"
                "From the extracted smartpro-host-preview folder, run:\n"
                "  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app python -m psp_shell --demo\n"
                "Headless: add --headless --frames 2 --state-dir /tmp/smartpro-preview-state.\n"
                "Mutable state belongs outside this payload. Do not reuse real ROMs/saves in demo mode.\n"
                "The .tar file beside this ZIP is signed by a development key, for explicit host fixture testing only.\n"
                "The included public key demonstrates signature integrity; it is not a production trust anchor.\n"
                "No firmware, emulators, upstream spruce/PyUI source, private signing keys or commercial game data are included.\n"
            ).encode("utf-8")
            entries = [("smartpro-host-preview/" + path.relative_to(payload).as_posix(), path.read_bytes())
                       for path in sorted(payload.rglob("*")) if path.is_file()]
            entries.append(("smartpro-host-preview/RUN.txt", preview_instructions))
            zip_name = release + "-host-preview.zip"
            zip_files(temporary_output / zip_name, entries, epoch)
            zip_files(scratch / "preview-rebuild.zip", entries, epoch)
            overlay.require((temporary_output / zip_name).read_bytes() == (scratch / "preview-rebuild.zip").read_bytes(),
                            "standalone ZIP rebuild differs")
            if include_source:
                source_name = release + "-original-source.zip"
                if snapshot is not None:
                    source_entries.append(("smartpro-original-source/metadata/release-source.json",
                                           overlay.canonical(snapshot) + b"\n"))
                zip_files(temporary_output / source_name, source_entries, epoch)
                zip_files(scratch / "source-rebuild.zip", source_entries, epoch)
                overlay.require((temporary_output / source_name).read_bytes() == (scratch / "source-rebuild.zip").read_bytes(),
                                "source ZIP rebuild differs")
            (temporary_output / "START-HERE.txt").write_bytes(preview_instructions)
            report = {
                "schema": 1, "release_id": release, "status": "host-development-preview",
                "source_date_epoch": epoch, "payload_files": file_count,
                "development_key_id": key_id, "signer": "ephemeral development" if generated_key else "explicit external development signer",
                "generated_private_key_deleted": generated_key,
                "private_key_packaged": False, "production_authenticity_claim": False,
                "byte_identical_overlay_rebuild_with_same_key": True,
                "byte_identical_unsigned_zip_rebuild": True,
                "signature_hash_inventory_verified": True,
                "payload_source_inventory_verified": True,
                "fixture_stage_activate_rollback": True,
                "smoke": smoke,
                "device_activation_qualified": False,
                "device_gates": {"hardware_qualified": False, "runtime_verified": False, "source_use_verified": False},
                "base_commit": overlay.SPRUCE_COMMIT, "pyui_git_tree": overlay.PYUI_TREE,
                "release_selection": selection,
            }
            if snapshot is not None:
                put_json(temporary_output / "release-source.json", snapshot)
            put_json(temporary_output / "build-report.json", report)
            if generated_key:
                # Delete before publishing, in addition to TemporaryDirectory cleanup.
                Path(private_key).unlink()
                overlay.require(not Path(private_key).exists(), "development private key was not removed")
        checksums = []
        for path in sorted(temporary_output.iterdir()):
            overlay.require(path.is_file() and not path.is_symlink(), "unexpected artifact entry")
            checksums.append(overlay.file_digest(path) + "  " + path.name + "\n")
        (temporary_output / "SHA256SUMS").write_text("".join(checksums), encoding="ascii")
        # Verify all final deliverable hashes before making the directory visible.
        for line in checksums:
            expected, name = line.rstrip("\n").split("  ", 1)
            overlay.require(overlay.file_digest(temporary_output / name) == expected, "artifact readback hash differs")
        os.rename(temporary_output, output)
        return {"output": str(output), "artifacts": sorted(path.name for path in output.iterdir()),
                "overlay_sha256": overlay.file_digest(output / archive_name), "smoke": report["smoke"],
                "device_activation_qualified": False}
    finally:
        if temporary_output.exists():
            shutil.rmtree(temporary_output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", help="must match the selected descriptor; omission uses its release_id")
    parser.add_argument("--release-descriptor", type=Path,
                        help="current selection JSON; defaults to <project>/packaging/current-release.json")
    parser.add_argument("--source-date-epoch", type=int,
                        help="normalized timestamp; defaults to SOURCE_DATE_EPOCH or descriptor timestamp")
    parser.add_argument("--source-lock", type=Path)
    parser.add_argument("--include-source", action="store_true")
    parser.add_argument("--smoke-python", type=Path, help="installed preview Python; exercises dummy-SDL rendering and installed contracts")
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--public-key", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.source_lock is None:
            embedded_lock = args.project / "metadata/spruce-source-lock.json"
            repository_lock = args.project.parent / "docs/spruce-source-lock.json"
            args.source_lock = (embedded_lock if embedded_lock.is_file() else
                                repository_lock if repository_lock.is_file() else None)
        descriptor_path = args.release_descriptor or args.project / "packaging/current-release.json"
        epoch = (args.source_date_epoch if args.source_date_epoch is not None else
                 int(os.environ["SOURCE_DATE_EPOCH"]) if "SOURCE_DATE_EPOCH" in os.environ else None)
        print(json.dumps(build(args.project, args.output, args.release, epoch,
                               source_lock=args.source_lock, include_source=args.include_source,
                               smoke_python=args.smoke_python, private_key=args.private_key,
                               public_key=args.public_key, release_descriptor=descriptor_path), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, overlay.OverlayError, subprocess.SubprocessError) as exc:
        print("development-release: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
