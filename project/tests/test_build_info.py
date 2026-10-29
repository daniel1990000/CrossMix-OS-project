# SPDX-License-Identifier: MIT
"""Version reports identify the loaded source/package, without qualification claims."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import psp_shell


class BuildInfoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="build-info-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.descriptor = {"schema": 1, "release_id": "smartpro-psp-0.1.0-dev42",
                           "delivery": "original-only-host-preview"}

    def info(self, module):
        with mock.patch.object(psp_shell, "__file__", str(module)):
            return psp_shell.build_info()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_source_version_follows_descriptor_without_inventing_a_commit(self):
        self.write(self.root / "project/packaging/current-release.json", self.descriptor)
        info = self.info(self.root / "project/psp_shell/__init__.py")
        self.assertEqual(info["version"], "0.1.0-dev42")
        self.assertEqual(info["source_kind"], "source-checkout")
        self.assertIsNone(info["frontend_commit"])
        self.assertIsNone(info["working_tree_modified"])

    def test_retropass_source_version_uses_its_mixed_source_descriptor(self):
        descriptor = {**self.descriptor, "release_id": "smartpro-retropass-0.1.0-dev19",
                      "delivery": "retropass-host-preview"}
        self.write(self.root / "project/packaging/current-release.json", descriptor)
        info = self.info(self.root / "project/psp_shell/__init__.py")
        self.assertEqual(info["version"], "0.1.0-dev19")
        self.assertEqual(info["release_id"], descriptor["release_id"])
        self.assertEqual(info["delivery"], "retropass-host-preview")
        self.assertEqual(info["source_kind"], "source-checkout")

    def test_installed_build_uses_its_retained_identity(self):
        package = self.root / "release"
        self.write(package / "metadata/development-release.json", {
            "schema": 1, "release_id": self.descriptor["release_id"],
            "release_selection": {"descriptor": self.descriptor,
                "frontend": {"commit": "a" * 40, "working_tree_modified": True},
                "source_inventory_sha256": "b" * 64}})
        info = self.info(package / "app/psp_shell/__init__.py")
        self.assertEqual(info["version"], "0.1.0-dev42")
        self.assertEqual(info["source_kind"], "installed-package")
        self.assertEqual(info["frontend_commit"], "a" * 40)
        self.assertTrue(info["working_tree_modified"])
        self.assertEqual(info["source_inventory_sha256"], "b" * 64)
        self.assertNotIn("hardware_qualified", info)

    def test_distribution_fallback_uses_the_same_installed_descriptor(self):
        prefix = self.root / "venv"
        self.write(prefix / "share/psp_shell/metadata/current-release.json", self.descriptor)
        with mock.patch.object(psp_shell.sys, "prefix", str(prefix)):
            info = self.info(prefix / "lib/site-packages/psp_shell/__init__.py")
        self.assertEqual(info["version"], "0.1.0-dev42")
        self.assertEqual(info["source_kind"], "installed-package")
        self.assertIsNone(info["frontend_commit"])

    def test_missing_invalid_oversized_or_inconsistent_metadata_is_unavailable(self):
        module = self.root / "release/app/psp_shell/__init__.py"
        self.assertEqual(self.info(module)["source_kind"], "unavailable")
        path = self.root / "release/metadata/development-release.json"
        for data in (b"broken", b"x" * (256 * 1024 + 1), json.dumps({
                "release_id": "wrong", "release_selection": {"descriptor": self.descriptor}}).encode()):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            with self.subTest(size=len(data)):
                info = self.info(module)
                self.assertEqual(info["version"], "unknown-development")
                self.assertIsNone(info["frontend_commit"])


if __name__ == "__main__":
    unittest.main()
