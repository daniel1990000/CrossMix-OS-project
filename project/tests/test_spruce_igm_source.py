# SPDX-License-Identifier: MIT
"""Real patched IGM C functions; host fixtures do not qualify an installed RA."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from retroarch.source_patch import HERE, prepare


def block(text, anchor, semicolon=False):
    begin = text.index(anchor)
    opening = text.index("{", begin)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[begin:index + 1 + int(semicolon)]
    raise ValueError("unclosed source block")


class IGMPatchedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("SPRUCE_RA_SOURCE_ROOT")
        if not source:
            raise unittest.SkipTest("Set SPRUCE_RA_SOURCE_ROOT to the locked spruceUI/RA recipe")
        cls.temporary = tempfile.TemporaryDirectory(prefix="igm-source-acceptance-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.source = Path(source)
        cls.prepared = cls.work / "prepared"
        cls.report = prepare(cls.source, cls.prepared)
        (cls.prepared / "boolean.h").write_text("#include <stdbool.h>\n")
        (cls.prepared / "retro_miscellaneous.h").write_text("#define PATH_MAX_LENGTH 4096\n")
        source = (cls.prepared / "spruce_igm.c").read_text()
        theme = (cls.prepared / "spruce_igm_theme.c").read_text()
        parts = {"SECTION": block(theme, "enum igm_section", True),
            "CONTEXT": block(theme, "typedef struct") + " igm_parse_ctx;",
            "COLOR": block(theme, "static bool igm_parse_color"),
            "DEFAULTS": block(theme, "static void igm_theme_set_defaults"),
            "COLOR_KEYS": block(theme, "static const struct") + " igm_color_keys[] = " +
                block(theme[theme.index("} igm_color_keys[] ="):], "{", True),
            "LABEL_KEYS": block(theme, "static const char *igm_label_keys", True),
            "MEMBER": block(theme, "static bool igm_on_member"),
            "OBJECT_START": block(theme, "static bool igm_on_object_start"),
            "OBJECT_END": block(theme, "static bool igm_on_object_end"),
            "STRING": block(theme, "static bool igm_on_string"),
            "BOOL": block(theme, "static bool igm_on_bool"),
            "ITEMS": block(source, "enum spruce_igm_item", True),
            "READ_BUTTONS": block(source, "static uint16_t igm_read_buttons"),
            "RESOLVE": block(source, "static void igm_project_menu_keys"),
            "HANDLE_INPUT": block(source, "static void igm_handle_input")}
        code = (HERE / "tests/igm_controls_acceptance.c.in").read_text()
        for name, content in parts.items():
            marker = "/*@@" + name + "@@*/"
            if code.count(marker) != 1:
                raise AssertionError("IGM source marker differs")
            code = code.replace(marker, content)
        (cls.prepared / "acceptance.c").write_text(code)
        cls.binary = cls.work / "igm-acceptance"
        result = subprocess.run(["gcc", "-std=gnu99", "-Wall", "-Wextra", "-Wno-unused-function", "-I", str(cls.prepared),
                        str(cls.prepared / "acceptance.c"), "-o", str(cls.binary)],
                       capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def scenario(self, name):
        subprocess.run([str(self.binary), name], check=True, capture_output=True, timeout=10)

    def test_legacy_and_disabled_policy_are_unchanged(self): self.scenario("defaults")
    def test_south_confirm_pair_handles_actual_source_save_and_back(self): self.scenario("south")
    def test_east_confirm_pair_handles_actual_source_save_and_back(self): self.scenario("east")
    def test_invalid_or_incomplete_pairs_fall_back_to_legacy(self): self.scenario("invalid")
    def test_nested_members_do_not_enable_controls(self): self.scenario("nested")
    def test_dpad_navigation_and_slot_changes_are_unchanged(self): self.scenario("navigation")
    def test_close_actions_wait_for_both_face_buttons_to_release(self): self.scenario("deferred")

    def test_changed_input_or_patch_is_refused_before_staging(self):
        lock = json.loads((HERE / "source-lock.json").read_text())
        for item in lock["inputs"]:
            self.assertEqual(hashlib.sha256((self.source / item["path"]).read_bytes()).hexdigest(), item["sha256"])
        self.assertFalse(self.report["full_engine_build"])
        self.assertFalse(self.report["device_qualified"])
        self.assertFalse(self.report["distribution_cleared"])


if __name__ == "__main__":
    unittest.main()
