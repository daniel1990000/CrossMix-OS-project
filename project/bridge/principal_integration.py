"""Stage one complete exact-source process-boundary integration for review.

This is an alternative to the retained/cooperative-audio experiment. It keeps
all existing PyUI workers until the principal observes the source process tree
exit. No function applies a patch, installs a module or enables qualification.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from .source_integration import SOURCE_BLOBS as LIFECYCLE_BLOBS, _replace_once
from .pyui_entry import MAIN_MENU_BLOB, MAIN_MENU_PATH
from psp_shell.runtime import ContractError, SPRUCE_COMMIT


PYUI = "App/PyUI/main-ui/"
MAINUI = PYUI + "mainui.py"
MIYOO = PYUI + "devices/miyoo_trim_common.py"
PRINCIPAL = "spruce/scripts/principal.sh"
SOURCE_BLOBS = {**LIFECYCLE_BLOBS,
    MAIN_MENU_PATH: MAIN_MENU_BLOB,
    MIYOO: "63467b26b5b8e1cb7b5508f448be8f200311fbce",
    "App/PyUI/launch.sh": "8e23351cdfbf28069b30bc3a3e58c2badb7bfcce",
    PYUI + "menus/games/utils/favorites_manager.py": "46bb73956ed4e975a7f008bef4ae61ebe45bd181",
    PYUI + "menus/games/utils/recents_manager.py": "e37d8eec5a2f29ed017eefdfc8b87136edbc865e",
    PYUI + "menus/games/utils/rom_info.py": "a989d731efb60d5c239cd7b173aa47b346ad46e7",
    PYUI + "menus/games/utils/rom_select_options_builder.py": "b8a4fbeba67f8d5479a33670dd09d9cb7a6d2fa9",
    PYUI + "utils/py_ui_config.py": "9de7d3859064e8eee22f71f7b6ee65ec0cc2a9c6",
    'App/PyUI/main-ui/utils/cfw_system_config.py': 'bc65758da4dad522f95700843475fe073f0c0940',
    'App/PyUI/main-ui/option_select_ui.py': 'd137e34a82f75133c83a437b173230d6377982e1',
    'spruce/scripts/bluetooth.sh': '5e7cc94e4e51dfd72a6bc83c31e47c5dc1ae031e',
    'spruce/scripts/wifi.sh': 'a8d337e08f25c6c44bbcce53833b6a49f280f958',
    'spruce/scripts/helperFunctions.sh': 'a415b749900c4a936093985639347ac1674d042d',
    'spruce/scripts/platform/device.sh': '0a82270e323672cd598a4db9dba14311b92ca919',
    'spruce/scripts/device_functions.sh': '0f9e28f698b6baa94b25f1acc9d3dff5f2388c31',
    'spruce/scripts/platform/SmartPro.cfg': '3d271678195b5fb547db1a0d31e11afe3086cce9',
    'spruce/scripts/platform/device_functions/SmartPro.sh': '5ed8fd031247840cf7c14585b934b9c1de192723',
    'spruce/scripts/platform/device_functions/trimui_a133p.sh': 'c295050b419776df00b737858bdd214bd43f9e6c',
    'spruce/scripts/platform/device_functions/a133p.sh': 'de6b074edfb2f5bc4315a3a7cdabb85dc4bb1b7f',
    'spruce/scripts/platform/device_functions/trimui_delegate.sh': '235739974fa302f1fbddf9c82edae4914e1447f1',
    'spruce/scripts/networkservices.sh': '3cb3eb01cecd1f06e57a8805bc67486e51fd7c1b',
    'spruce/scripts/network/sambaFunctions.sh': 'c5ab3e4c641e1dc03c90183fdf5bc1e103cf8f06',
    'spruce/scripts/network/sshFunctions.sh': '2893e7f83202ef78b589da60930672ceb16e3e8b',
    'spruce/scripts/network/sftpgoFunctions.sh': 'd326c7094047b22c62a1efb1e4c1b7dc9b6dfd85',
    'spruce/scripts/network/syncthingFunctions.sh': '17153236f9dd368117285ed87d885e13b5194c7f',
    'spruce/scripts/network/darkhttpdFunctions.sh': '65a1a281c01cfdc5787f45ced21f2bf12a5cab07',
    'spruce/scripts/network/raproxyFunctions.sh': '7213c5f3b8e6d718f80d6ad52c2ee90479de0a9e',
    'spruce/scripts/network/timeFunctions.sh': 'af9892bce2a70caedfb59871530dcc4b09314b38',
    'spruce/scripts/applySetting/networkServiceToggle.sh': 'cadc981b76be81506ff20faaf571a97f515ef4aa',
    'spruce/scripts/tasks/clearwifi.sh': '9f82ff813b005b0f661e13238e912b533d4bd893',
    'spruce/scripts/tasks/updateRAOfflineProxy.sh': '1568d2f1b7cc55647947c5cfddf78e4d5204abae',
    'spruce/scripts/asound-setup.sh': '81a28c190efd2c56ae58d5be7a7e5359bfe1340d',
    'spruce/scripts/bin/spruce_bluetooth': 'bae56f4f8b1330bf2b6edc71df0904b4b9b0740a',
    'spruce/scripts/bin/spruce_wifi': '2b388ad9e29a05486ec15d836620e255e8a1cbf5',
}
# Every original Python module in the fixed payload participates in the
# independent device expected-hash inventory, including transitive imports.
REQUIRED_PROJECT_MODULES = [
    'app/bridge/__init__.py',
    'app/bridge/bootstrap.py',
    'app/bridge/frontend.py',
    'app/bridge/lifecycle.py',
    'app/bridge/principal.py',
    'app/bridge/principal_integration.py',
    'app/bridge/process_source.py',
    'app/bridge/pyui_entry.py',
    'app/bridge/qualified_runtime.py',
    'app/bridge/resident.py',
    'app/bridge/source_integration.py',
    'app/psp_shell/__init__.py',
    'app/psp_shell/__main__.py',
    'app/psp_shell/adapters/spruce.py',
    'app/psp_shell/app.py',
    'app/psp_shell/controls.py',
    'app/psp_shell/demo.py',
    'app/psp_shell/embedded.py',
    'app/psp_shell/hardware_settings.py',
    'app/psp_shell/health.py',
    'app/psp_shell/library.py',
    'app/psp_shell/ports.py',
    'app/psp_shell/ppsspp.py',
    'app/psp_shell/runtime.py',
    'app/psp_shell/settings.py',
    'app/psp_shell/state_evidence.py',
    'app/psp_shell/ui/__init__.py',
    'app/psp_shell/ui/artwork.py',
    'app/psp_shell/ui/input.py',
    'app/psp_shell/ui/model.py',
    'app/psp_shell/ui/renderer.py',
    'app/psp_shell/ui/text.py',
]


def _checked(root, name):
    path = root / name
    if (not path.is_file() or path.stat().st_size > 262144 or
            any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents)):
        raise ContractError("SOURCE_MISMATCH", "Process integration requires bounded regular pinned sources")
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if blob != SOURCE_BLOBS[name]:
        raise ContractError("SOURCE_MISMATCH", "A process integration source differs from pinned spruce v4.5.4")
    return raw


def stage_process_exit_integration(source_root, staging_dir, *, source_use_verified=False,
        module_root="/mnt/SDCARD/App/PSPMode/integration/app"):
    if source_use_verified is not True:
        raise ContractError("SOURCE_USE_UNVERIFIED", "Resolve source-use obligations before producing the process-boundary derivative")
    if (not isinstance(module_root, str) or not module_root.startswith("/mnt/SDCARD/App/PSPMode/") or
            str(PurePosixPath(module_root)) != module_root or ".." in PurePosixPath(module_root).parts or
            re.fullmatch(r"/[A-Za-z0-9_./-]+", module_root) is None):
        raise ContractError("INVALID_MODULE_ROOT", "Use a fixed reviewed original-payload installation path under App/PSPMode")
    root, staging = Path(source_root).resolve(strict=True), Path(staging_dir).absolute()
    try:
        staging.resolve().relative_to(root)
    except ValueError:
        pass
    else:
        raise ContractError("UNSAFE_STAGING", "Process integration staging must be outside the original source")
    if any(p.is_symlink() for p in (staging, *staging.parents)):
        raise ContractError("UNSAFE_STAGING", "Process integration staging cannot use symlink directories")
    sources = {name: _checked(root, name) for name in SOURCE_BLOBS}
    patches, transformed = [], []
    for name in (MAINUI, MAIN_MENU_PATH, MIYOO, PYUI + "devices/device_common.py",
                 PYUI + "devices/trimui/trim_ui_smart_pro.py", PYUI + "utils/cfw_system_config.py",
                 PYUI + "option_select_ui.py", PRINCIPAL):
        raw = sources[name]
        text = raw.decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        if name == MAINUI:
            marker = "def start_background_threads():" + nl
            addition = nl.join(("    try:",
                "        from bridge.process_source import begin_process_source_tasks",
                "    except (ImportError, SyntaxError):",
                "        begin_process_source_tasks = None",
                "    if begin_process_source_tasks is not None:",
                "        project_tasks = begin_process_source_tasks(Device.get_device(), background_startup)",
                "        if project_tasks is not None:", "            return project_tasks", ""))
            changed = _replace_once(text, marker, marker + addition + nl)
            marker = "    start_background_threads()" + nl
            changed = _replace_once(changed, marker, nl.join((
                "    project_tasks = start_background_threads()",
                "    if project_tasks is not None:",
                "        from bridge.process_source import bind_initialized_source",
                "        from menus.games.utils.rom_select_options_builder import get_rom_select_options_builder",
                "        bind_initialized_source(main_menu, project_tasks, get_rom_select_options_builder())", "")))
        elif name == MAIN_MENU_PATH:
            marker = "        self.check_for_gameswitcher()" + nl + "        self.check_for_boxart_resizing()" + nl
            addition = nl.join(("        try:",
                "            from bridge.pyui_entry import maybe_run_main_menu",
                "        except (ImportError, SyntaxError):", "            maybe_run_main_menu = None",
                "        if maybe_run_main_menu is not None and maybe_run_main_menu(self):", "            return", "", ""))
            changed = _replace_once(text, marker, marker + addition)
        elif name == MIYOO:
            marker = "    def write_cmd_to_run(command):" + nl
            addition = nl.join(("        try:", "            from bridge.process_source import stage_existing_command",
                "        except (ImportError, SyntaxError):", "            stage_existing_command = None",
                "        if stage_existing_command is not None and stage_existing_command(command):", "            return", ""))
            changed = _replace_once(text, marker, marker + addition + nl)
            marker = '    def run_game(device, rom_info: RomInfo, remap_sdcard_path = True, run_prefix ="") -> subprocess.Popen:' + nl
            addition = nl.join(("        try:", "            from bridge.process_source import capture_existing_game",
                "        except (ImportError, SyntaxError):", "            capture_existing_game = None",
                "        if capture_existing_game is not None:", "            capture_existing_game(rom_info)", ""))
            changed = _replace_once(changed, marker, marker + addition + nl)
        elif name == PYUI + "devices/device_common.py":
            changed = text
            for radio in ("bluetooth", "wifi"):
                marker = "        cmd = PyUiConfig.get_" + radio + "_cmd()" + nl
                addition = nl.join(("        try:", "            from bridge.resident import delegate_radio",
                    "        except (ImportError, SyntaxError):", "            delegate_radio = None",
                    "        if delegate_radio is not None and delegate_radio(" + repr(radio) + ", cmd, args" +
                        (", stdin_text=stdin_text" if radio == "wifi" else "") + "):",
                    '            return ""', ""))
                changed = _replace_once(changed, marker, marker + addition)
        elif name == PYUI + "devices/trimui/trim_ui_smart_pro.py":
            marker = ('        subprocess.run(["/bin/sh", "-c", f". {self.SPRUCE_HELPER_FUNCTIONS} && restart_trimui_inputd"],' + nl +
                '                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,' + nl +
                '                       timeout=30, check=True)' + nl)
            addition = nl.join(("        try:", "            from bridge.resident import delegate",
                "        except (ImportError, SyntaxError):", "            delegate = None",
                '        if delegate is None or not delegate("input-calibration"):',
                '    ' + marker.replace(nl, nl + "    ").rstrip(), ""))
            changed = _replace_once(text, marker, addition)
        elif name == PYUI + "utils/cfw_system_config.py":
            marker = '                    subprocess.run(command + [str(selected_value)], check=True)'
            addition = nl.join(("                    try:", "                        from bridge.resident import delegate_known_command",
                "                    except (ImportError, SyntaxError):", "                        delegate_known_command = None",
                "                    if delegate_known_command is None or not delegate_known_command(command + [str(selected_value)]):",
                "    " + marker))
            changed = _replace_once(text, marker, addition)
        elif name == PYUI + "option_select_ui.py":
            marker = "import subprocess"
            addition = nl.join((marker, "try:", "    from bridge.resident import run_source_shell",
                "except (ImportError, SyntaxError):", "    def run_source_shell(command):",
                "        return subprocess.run(command, shell=True)"))
            changed = _replace_once(text, marker, addition)
            if changed.count("subprocess.run(val, shell=True)") != 4:
                raise ContractError("SOURCE_MISMATCH", "The pinned source task execution seams changed")
            changed = changed.replace("subprocess.run(val, shell=True)", "run_source_shell(val)")
        else:
            marker = ". /mnt/SDCARD/spruce/scripts/helperFunctions.sh" + nl
            addition = nl.join(("", "# A prior dirty lifetime blocks fallback even if original modules/config are unavailable.",
                'if [ -e /tmp/trimui-project-principal/dirty ] || [ -L /tmp/trimui-project-principal/dirty ]; then',
                '    log_message "Prior project source/process boundary remains incomplete; no UI started"', "    exit 125", "fi", "",
                "# Fixed reviewed original modules; no card selector supplies executable paths.",
                "project_boundary_enabled=0", "project_boundary() {",
                '    PYTHONPATH="' + module_root + '" /mnt/SDCARD/spruce/flip/bin/MainUI -m bridge.principal "$@"',
                "}", 'if [ "$PLATFORM" = "SmartPro" ] && [ -f "' + module_root + '/bridge/principal.py" ]; then',
                "    project_boundary status", "    project_boundary_status=$?", '    case "$project_boundary_status" in',
                "        0) project_boundary_enabled=1 ;;", "        64) ;;",
                '        *) log_message "Project principal qualification/ownership check blocked; no UI started"; exit 125 ;;',
                "    esac", "fi",
                'if [ "$project_boundary_enabled" -eq 1 ]; then',
                '    PYTHONPATH="' + module_root + '" /mnt/SDCARD/spruce/flip/bin/MainUI -m bridge.principal resident &',
                '    TRIMUI_PROJECT_RESIDENT_SERVER=$!', "    export TRIMUI_PROJECT_RESIDENT_SERVER",
                '    project_boundary resident-ready "$TRIMUI_PROJECT_RESIDENT_SERVER" || { log_message "Shared resident authority unavailable; no UI started"; exit 125; }',
                "fi", ""))
            changed = _replace_once(text, marker, marker + addition + nl)
            marker = "        /mnt/SDCARD/App/PyUI/launch.sh" + nl
            changed = _replace_once(changed, marker, nl.join((
                '        if [ "$project_boundary_enabled" -eq 1 ]; then',
                '            project_boundary pyui || { log_message "Source process descendants remain uncertain; no game or second UI started"; exit 125; }',
                "        else", "            /mnt/SDCARD/App/PyUI/launch.sh", "        fi", "")))
            marker = "        /tmp/cmd_to_run.sh >/dev/null 2>&1" + nl + "        cmd_exit_code=$?" + nl
            changed = _replace_once(changed, marker, nl.join((
                '        if [ "$project_boundary_enabled" -eq 1 ]; then',
                '            project_boundary command || { log_message "Foreground descendants or staged command remain uncertain; no second UI started"; exit 125; }',
                "            cmd_exit_code=0 # Boundary completion; emulator/save success is separate evidence.",
                "        else", "            /tmp/cmd_to_run.sh >/dev/null 2>&1", "            cmd_exit_code=$?", "        fi", "")))
            marker = "        rm /tmp/cmd_to_run.sh" + nl
            changed = _replace_once(changed, marker, '        [ ! -e /tmp/cmd_to_run.sh ] || rm /tmp/cmd_to_run.sh' + nl)
        if name.endswith(".py"):
            compile(changed, name, "exec")
        patches.extend(difflib.unified_diff(text.splitlines(keepends=True), changed.splitlines(keepends=True),
                                           fromfile="a/" + name, tofile="b/" + name))
        transformed.append({"path": name, "base_sha256": hashlib.sha256(raw).hexdigest(),
                            "patched_sha256": hashlib.sha256(changed.encode("utf-8")).hexdigest()})
    staging.mkdir(parents=True, exist_ok=True)
    patch = staging / "0001-pyui-principal-process-boundary.patch"
    metadata = staging / "process-boundary-hook.json"
    if patch.is_symlink() or metadata.is_symlink():
        raise ContractError("UNSAFE_STAGING", "Process integration artifacts cannot replace symlinks")
    patch.write_bytes("".join(patches).encode("utf-8"))
    record = {"schema": 1, "base_commit": SPRUCE_COMMIT, "integration_mode": "principal-process-exit",
        "module_root": module_root, "patch": patch.name, "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
        "sources": [{"path": p, "git_blob": SOURCE_BLOBS[p], "sha256": hashlib.sha256(b).hexdigest()} for p, b in sources.items()],
        "transformed": transformed, "changed_paths": [item["path"] for item in transformed],
        "required_project_modules": REQUIRED_PROJECT_MODULES, "source_use_verified": True,
        "hardware_execution_enabled": False, "requires_independently_qualified_fixed_runtime": True,
        "modifies_rootfs_or_boot": False, "requires_legacy_lifecycle_hook": False,
        "supplies_main_menu_hook": True}
    record["resident_delegation"] = {"owner": "existing-principal-sibling", "authenticated_private_ipc": True,
        "operations": ["bluetooth-apply", "wifi", "input-calibration", "network-service", "task"],
        "claims_service_writers_stopped": False, "game_inherits_capability": False,
        "source_completion_requires_authenticated_echild_record": True}
    metadata.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
