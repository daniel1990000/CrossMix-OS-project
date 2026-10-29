# SPDX-License-Identifier: MIT
"""Verify actual imported bytes and packaged corresponding source, not screenshots."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packaging"))
sys.path.insert(0, str(PROJECT / "tools"))
import dev_release
import overlay
import release_descriptor
from build_payload import build_payload


class RetroPassProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = dict(dev_release.original_source_entries(PROJECT))
        cls.lock = json.loads(cls.entries["smartpro-original-source/retropass/source-lock.json"])

    def test_complete_upstream_tree_includes_code_assets_docs_and_authors(self):
        lock = release_descriptor.validate_retropass_vendor(PROJECT, self.entries)
        self.assertEqual(lock["file_count"], 177)
        self.assertEqual(sum(row["size"] for row in lock["files"]), 9560952)
        for name in ("RetroPass/MainPage.xaml", "RetroPass/Playlist.cs",
                     "RetroPass/DataSourceEmulationStation.cs", "Docs/menu.gif",
                     "LICENSE.txt", "AUTHORS.md", ".github/workflows/main.yml"):
            self.assertIn("smartpro-original-source/vendor/retropass/" + name, self.entries)
        self.assertNotIn("smartpro-original-source/vendor/retropass/.git/config", self.entries)

    def test_missing_changed_extra_and_reinventoried_source_are_rejected(self):
        key = "smartpro-original-source/vendor/retropass/RetroPass/Playlist.cs"
        for kind in ("missing", "changed", "extra", "reinventoried"):
            with self.subTest(kind=kind):
                entries = dict(self.entries)
                if kind == "missing":
                    entries.pop(key)
                elif kind == "changed":
                    entries[key] += b"changed"
                elif kind == "extra":
                    entries["smartpro-original-source/vendor/retropass/injected.py"] = b"unexpected"
                else:
                    lock = json.loads(entries["smartpro-original-source/retropass/source-lock.json"])
                    lock["files"][0]["sha256"] = "0" * 64
                    entries["smartpro-original-source/retropass/source-lock.json"] = json.dumps(lock).encode()
                with self.assertRaises(overlay.OverlayError):
                    release_descriptor.validate_retropass_vendor(PROJECT, entries)

    def test_payload_retains_adapted_and_complete_upstream_source_with_gpl_notices(self):
        with tempfile.TemporaryDirectory(prefix="retropass-payload-") as temp:
            target = Path(temp) / "payload"
            build_payload(PROJECT, target)
            for row in self.lock["files"]:
                self.assertEqual((target / "notices/RetroPass-source" / row["path"]).read_bytes(),
                                 self.entries["smartpro-original-source/vendor/retropass/" + row["path"]])
            self.assertTrue((target / "app/retropass/library.py").is_file())
            self.assertEqual((target / "notices/RetroPass-GPL-2.0.txt").read_bytes(),
                             (PROJECT / "vendor/retropass/LICENSE.txt").read_bytes())
            self.assertEqual((target / "notices/RetroPass-NOTICE.txt").read_bytes(),
                             (PROJECT / "retropass/NOTICE.txt").read_bytes())
            provenance = json.loads((target / "metadata/source-provenance.json").read_bytes())
            self.assertTrue(provenance["upstream_source_bundled"])
            self.assertEqual(provenance["licence_scopes"]["retropass"], "GPL-2.0-only")
            self.assertEqual(provenance["retropass"]["commit"], self.lock["commit"])

    def test_source_capture_materializes_the_complete_tree_for_no_git_rebuilds(self):
        with tempfile.TemporaryDirectory(prefix="retropass-source-capture-") as temp:
            target = Path(temp) / "captured"
            inventory = dev_release.materialize_source(list(self.entries.items()), target)
            self.assertEqual(release_descriptor.validate_retropass_vendor(target)["commit"], self.lock["commit"])
            self.assertIn("vendor/retropass/RetroPass/MainPage.xaml", inventory)
            self.assertFalse((target / "vendor/retropass/.git").exists())


if __name__ == "__main__":
    unittest.main()
