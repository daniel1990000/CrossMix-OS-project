# SPDX-License-Identifier: MIT
"""Apply and execute a narrow acceptance build from the locked PPSSPP source.

The compiled fixtures combine the actual patched functions with explicit stubs
for unrelated platform/UI services. This is not a full emulator or device test.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = ROOT / "source-lock.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def block(source: str, marker: str, *, semicolon: bool = False) -> str:
    """Extract an exact C++ block, respecting comments and quoted strings."""
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    state = "code"
    pos = opening
    while pos < len(source):
        char = source[pos]
        following = source[pos:pos + 2]
        if state in ("string", "character"):
            if char == "\\":
                pos += 2
                continue
            if char == ('"' if state == "string" else "'"):
                state = "code"
        elif state == "line":
            if char == "\n":
                state = "code"
        elif state == "comment":
            if following == "*/":
                state = "code"
                pos += 2
                continue
        elif following in ("//", "/*"):
            state = "line" if following == "//" else "comment"
            pos += 2
            continue
        elif char in ('"', "'"):
            state = "string" if char == '"' else "character"
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                if semicolon:
                    if source[end:end + 1] != ";":
                        raise AssertionError("expected semicolon after " + marker)
                    end += 1
                return source[start:end]
        pos += 1
    raise AssertionError("unclosed C++ block: " + marker)


def checked(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                            timeout=90, check=False)
    if result.returncode:
        raise AssertionError(f"{command!r} failed ({result.returncode})\n"
                             f"{result.stdout}\n{result.stderr}")
    return result


class PatchMetadataTests(unittest.TestCase):
    def test_patch_and_license_match_lock(self):
        lock = json.loads(LOCK.read_text())
        self.assertEqual(lock["upstream"]["commit"],
                         "d357e6a32934800d3d80b49f910a603e1b069751")
        self.assertFalse(lock["qualification"]["device_tested"])
        self.assertIsNone(lock["qualification"]["installed_executable_sha256"])
        for patch in lock["patches"]:
            self.assertEqual(sha256((ROOT / patch["path"]).read_bytes()),
                             patch["sha256"])
        self.assertEqual(sha256((ROOT / "LICENSE.PPSSPP.txt").read_bytes()),
                         lock["upstream"]["license_sha256"])


class PatchedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_value = os.environ.get("PPSSPP_SOURCE_ROOT")
        if not source_value:
            raise unittest.SkipTest("Set PPSSPP_SOURCE_ROOT to the pinned v1.20.3 checkout")
        cls.source = Path(source_value).resolve()
        cls.lock = json.loads(LOCK.read_text())
        if not shutil.which("g++") or not shutil.which("git"):
            raise AssertionError("Acceptance requires git and g++ (C++17)")
        cls.temp = tempfile.TemporaryDirectory(prefix="ppsspp-menu-acceptance-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        for item in cls.lock["source_files"]:
            path = cls.source / item["path"]
            if not path.is_file():
                raise AssertionError("Missing locked sparse source file: " + str(path))
            data = path.read_bytes()
            if sha256(data) != item["sha256"]:
                raise AssertionError("Pinned source preimage differs: " + str(path))
            target = cls.work / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for patch in cls.lock["patches"]:
            path = ROOT / patch["path"]
            checked(["git", "apply", "--check", str(path)], cwd=cls.work)
            checked(["git", "apply", str(path)], cwd=cls.work)
        for item in cls.lock["patched_files"]:
            if sha256((cls.work / item["path"]).read_bytes()) != item["sha256"]:
                raise AssertionError("Patched file differs: " + item["path"])
        cls._build_keymap()
        cls._build_settings()
        cls._build_ui()

    @classmethod
    def _compile(cls, name: str, substitutions: dict[str, str], *, sdl: bool = True):
        template = (HERE / (name + ".cpp.in")).read_text()
        for marker, value in substitutions.items():
            token = "/*@@" + marker + "@@*/"
            if template.count(token) != 1:
                raise AssertionError("fixture marker differs: " + marker)
            template = template.replace(token, value)
        if "/*@@" in template:
            raise AssertionError("unexpanded fixture marker")
        cpp = cls.work / (name + ("" if sdl else "_no_sdl") + ".cpp")
        cpp.write_text(template)
        binary = cpp.with_suffix("")
        command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Wno-type-limits",
                   "-Wno-unused-parameter", "-I", str(cls.work)]
        if sdl:
            command.append("-DSDL=1")
        command += [str(cpp), "-o", str(binary)]
        checked(command, cwd=cls.work)
        return binary

    @classmethod
    def _config_members(cls) -> str:
        text = (cls.work / "Core/Config.h").read_text()
        first = text.index("\tbool bProjectIndependentMenuControls")
        return text[first:text.index("\n\t// SystemParam", first)]

    @classmethod
    def _build_keymap(cls):
        source = (cls.work / "Core/KeyMap.cpp").read_text()
        state = (cls.work / "Common/Input/InputState.h").read_text()
        sdl = (cls.work / "SDL/SDLJoystick.cpp").read_text()
        ctrl = (cls.work / "Core/HLE/sceCtrl.h").read_text()
        utility = (cls.work / "Core/HLE/sceUtility.h").read_text()
        substitutions = {
            "INPUT_DEVICE": block(state, "enum InputDeviceID", semicolon=True),
            "INPUT_MAPPING": state[state.index("static const int AXIS_BIND_NKCODE_START"):
                                   state.index("// Be careful about changing these values")],
            "PSP_CONSTANTS": "\n".join(line for line in (ctrl + utility).splitlines()
                                          if re.match(r"#define (CTRL_|PSP_SYSTEMPARAM_BUTTON_)", line)),
            "CONFIG_MEMBERS": cls._config_members(),
            "SDL_TRANSLATOR": block(sdl, "InputKeyCode SDLJoystick::getKeycodeForButton"),
            "INSERT_MAPPING": block(source, "static void InsertIntoVector"),
            "HAS_MAIN_BUTTON": block(source, "bool HasMainButtonMapping"),
            "UPDATE_MENU": block(source, "void UpdateNativeMenuKeys()"),
        }
        cls.keymap = cls._compile("native_menu_acceptance", substitutions)
        cls.keymap_no_sdl = cls._compile("native_menu_acceptance", substitutions, sdl=False)

    @classmethod
    def _build_settings(cls):
        source = (cls.work / "Core/Config.cpp").read_text()
        header = (cls.work / "Core/ConfigSettings.h").read_text()
        settings = (cls.work / "Core/ConfigSettings.cpp").read_text()
        values = (cls.work / "Core/ConfigValues.h").read_text()
        actual_class = header[header.index("enum class CfgFlag"):]
        cls.config_binary = cls._compile("config_acceptance", {
            "CONFIG_TYPES": "\n".join(block(values, marker, semicolon=True) for marker in
                                       ("struct ConfigBlock", "struct ConfigTouchPos", "struct ConfigCustomButton")),
            "CONFIG_SETTING": actual_class,
            "CONFIG_MEMBERS": cls._config_members(),
            "READ_CONFIG": block(settings, "bool ConfigSetting::ReadFromIniSection"),
            "WRITE_CONFIG": block(settings, "void ConfigSetting::WriteToIniSection"),
            "PROJECT_SETTINGS": block(source, "static const ConfigSetting projectNativeMenuSettings[]", semicolon=True),
        })

    @classmethod
    def _build_ui(cls):
        source = (cls.work / "UI/GameSettingsScreen.cpp").read_text()
        popup = (cls.work / "Common/UI/PopupScreens.h").read_text()
        i18n = (cls.work / "Common/Data/Text/I18n.h").read_text()
        signature_start = popup.index("\tPopupMultiChoiceDynamic(std::string *value")
        signature = popup[signature_start:popup.index("\n\t\t: UI::PopupMultiChoice", signature_start)]
        start = source.index("#if defined(SDL)\n\tCheckBox *independentMenu")
        end = source.index("#endif", start) + len("#endif")
        self_type = "std::string_view T(std::string_view key, std::string_view def = \"\");"
        if self_type not in i18n:
            raise AssertionError("actual I18NCategory::T signature changed")
        cls.ui_binary = cls._compile("ui_acceptance", {
            "CONFIG_MEMBERS": cls._config_members(),
            "POPUP_SIGNATURE": signature,
            "PROJECT_UI": source[start:end],
        })

    def _run(self, binary: Path, scenario: str):
        result = checked([str(binary), scenario], cwd=self.work)
        self.assertIn("PASS " + scenario, result.stdout)

    def test_legacy_defaults_and_both_psp_preferences(self):
        self._run(self.keymap, "legacy")

    def test_physical_south_east_uses_actual_sdl_translation(self):
        self._run(self.keymap, "physical")

    def test_gameplay_remaps_and_psp_preference_do_not_change_native_menu(self):
        self._run(self.keymap, "remapped")

    def test_invalid_or_equal_pairs_fall_back_without_changing_outputs(self):
        self._run(self.keymap, "malformed")

    def test_keyboard_mouse_and_other_navigation_preserved(self):
        self._run(self.keymap, "navigation")

    def test_non_sdl_backend_keeps_original_policy(self):
        self._run(self.keymap_no_sdl, "no-sdl")

    def test_actual_config_setting_read_write_defaults_and_scoping(self):
        self._run(self.config_binary, "serialization")

    def test_native_ui_actions_set_complementary_pair_and_refresh(self):
        self._run(self.ui_binary, "widgets")

    def test_section_registry_and_no_gameplay_writer_in_patch(self):
        config = (self.work / "Core/Config.cpp").read_text()
        self.assertIn('{ &g_Config, projectNativeMenuSettings, ARRAY_SIZE(projectNativeMenuSettings), "ProjectNativeMenu" }', config)
        patch = (ROOT / self.lock["patches"][0]["path"]).read_text()
        added = "\n".join(line[1:] for line in patch.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        self.assertNotRegex(added, r"g_controllerMap\s*(\[|=|\.)")
        self.assertNotRegex(added, r"iButtonPreference\s*=")
        self.assertNotIn("SaveToIni(", added)


if __name__ == "__main__":
    unittest.main()
