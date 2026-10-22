# SPDX-License-Identifier: MIT
"""Execute pinned-script assembly gates against real disposable Git source."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ppsspp_apply_recipe", Path(__file__).resolve().parents[1] / "apply_recipe.py")
recipe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RecipeAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ppsspp-recipe-assembly-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.context = self.root / "recipe"
        self.output = self.root / "output"
        for path in (self.source, self.context, self.output):
            path.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.source, check=True)
        (self.source / "source.txt").write_text("upstream\n")
        subprocess.run(["git", "add", "."], cwd=self.source, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "Pinned fixture"], cwd=self.source, check=True)
        (self.source / "source.txt").write_text("project\n")
        self.lock = {"upstream": {"commit": recipe.git(self.source, "rev-parse", "HEAD").decode().strip()},
                     "patches": [{"sha256": "a" * 64}],
                     "patched_files": [{"path": "source.txt", "sha256": sha(b"project\n")}]}
        script = '''# Apply common patches
case "$patch" in
    fullscreen.py) echo "Skipping: fullscreen" ;;
    skip-vulkan-probe.py) echo "Skipping: probe" ;;
esac
# Apply PVR-specific patches
case "$patch" in
    revert-fullscreen.py|debug-gl-init.py|glfinish-before-swap.py) echo "Skipping: pvr" ;;
esac
mkdir -p build && cd build
'''
        self.files = {"build-pvr.sh": script}
        self.files["patches/common/selected.py"] = "from pathlib import Path\nPath('source.txt').write_text('common\\n')\n"
        self.files["patches/pvr/selected.py"] = "from pathlib import Path\nPath('source.txt').write_text('pvr\\n')\n"
        for group, names in (("common", ["fullscreen.py", "skip-vulkan-probe.py"]),
                             ("pvr", ["revert-fullscreen.py", "debug-gl-init.py", "glfinish-before-swap.py"])):
            for name in names:
                self.files["patches/" + group + "/" + name] = "raise RuntimeError('Skipped script must not execute')\n"
        self.inputs = {"recipe_commit": "b" * 40, "recipe_files": []}
        for name, content in self.files.items():
            path = self.context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            self.inputs["recipe_files"].append({"path": name, "sha256": recipe.digest(path)})

    def replace_script(self, path, content):
        (self.context / path).write_text(content)
        for item in self.inputs["recipe_files"]:
            if item["path"] == path:
                item["sha256"] = recipe.digest(self.context / path)

    def assemble(self):
        return recipe.assemble(self.source, self.context, self.lock, self.inputs, self.output)

    def test_selected_scripts_execute_in_order_with_exact_per_file_postimages(self):
        result = self.assemble()
        self.assertEqual(result["status"], "applied")
        self.assertEqual([item["path"] for item in result["scripts"]],
                         ["patches/common/selected.py", "patches/pvr/selected.py"])
        self.assertEqual(result["scripts"][0]["changed_files"], [{"path": "source.txt",
                         "before_sha256": sha(b"project\n"), "after_sha256": sha(b"common\n")}])
        self.assertEqual(result["final_source_files"]["source.txt"], sha(b"pvr\n"))
        self.assertEqual(len(result["skipped_by_pinned_recipe"]), 5)
        self.assertIn(b"+pvr", (self.output / "combined-tracked-source.patch").read_bytes())
        self.assertEqual(self.assemble(), result)  # Verified resume does not reapply patches.
        (self.source / "source.txt").write_text("external edit\n")
        with self.assertRaisesRegex(ValueError, "stale or has changed source"):
            self.assemble()
        (self.source / "source.txt").write_text("pvr\n")
        subprocess.run(["git", "add", "."], cwd=self.source, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "Different head"], cwd=self.source, check=True)
        with self.assertRaisesRegex(ValueError, "source commit differs"):
            self.assemble()

    def test_nonzero_exit_and_noop_scripts_cannot_qualify_assembly(self):
        self.replace_script("patches/common/selected.py", "raise SystemExit(9)\n")
        with self.assertRaisesRegex(ValueError, "script failed or changed no source"):
            self.assemble()
        report = json.loads((self.output / "recipe-assembly.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["scripts"][0]["exit_code"], 9)
        (self.output / "recipe-assembly.json").unlink()
        self.replace_script("patches/common/selected.py", "print('no source changed')\n")
        with self.assertRaisesRegex(ValueError, "script failed or changed no source"):
            self.assemble()
        self.assertEqual((self.source / "source.txt").read_text(), "project\n")

    def test_post_recipe_override_requires_exact_recipe_postimage_and_verified_patch(self):
        patch_data=b"--- a/source.txt\n+++ b/source.txt\n@@ -1 +1 @@\n-pvr\n+checked-completion\n"
        path=self.output/'completion.patch';path.write_bytes(patch_data)
        override={"upstream_commit":self.lock["upstream"]["commit"],"recipe_commit":self.inputs["recipe_commit"],
                  "source_files":[{"path":"source.txt","sha256":sha(b'pvr\n')}],
                  "patches":[{"path":"completion.patch","sha256":sha(patch_data)}],
                  "patched_files":[{"path":"source.txt","sha256":sha(b'checked-completion\n')}]}
        result=recipe.assemble(self.source,self.context,self.lock,self.inputs,self.output,override,self.output)
        self.assertEqual((self.source/'source.txt').read_text(),'checked-completion\n')
        self.assertEqual(result['post_recipe_overrides'],override['patches'])
        self.assertEqual(recipe.assemble(self.source,self.context,self.lock,self.inputs,self.output,override,self.output),result)
        path.write_bytes(b'changed override')
        with self.assertRaisesRegex(ValueError,'override patch changed'):
            recipe.assemble(self.source,self.context,self.lock,self.inputs,self.output,override,self.output)

    def test_post_recipe_mismatched_preimage_cannot_qualify_assembly(self):
        patch_data=b"--- a/source.txt\n+++ b/source.txt\n@@ -1 +1 @@\n-pvr\n+checked\n"
        (self.output/'completion.patch').write_bytes(patch_data)
        override={"upstream_commit":self.lock['upstream']['commit'],"recipe_commit":self.inputs['recipe_commit'],
                  "source_files":[{"path":"source.txt","sha256":sha(b'different recipe\n')}],
                  "patches":[{"path":"completion.patch","sha256":sha(patch_data)}],
                  "patched_files":[{"path":"source.txt","sha256":sha(b'checked\n')}]}
        with self.assertRaisesRegex(ValueError,'override source preimage differs'):
            recipe.assemble(self.source,self.context,self.lock,self.inputs,self.output,override,self.output)
        report=json.loads((self.output/'recipe-assembly.json').read_text())
        self.assertEqual(report['status'],'failed')

    def test_unlocked_script_or_different_skip_policy_refuses_before_changes(self):
        (self.context / "patches/common/selected.py").write_text("raise RuntimeError('unlocked')\n")
        with self.assertRaisesRegex(ValueError, "Pinned recipe content differs"):
            self.assemble()
        self.replace_script("patches/common/selected.py", self.files["patches/common/selected.py"])
        self.replace_script("build-pvr.sh", self.files["build-pvr.sh"].replace("fullscreen.py)", "different.py)"))
        with self.assertRaisesRegex(ValueError, "patch selection changed"):
            self.assemble()
        self.assertEqual((self.source / "source.txt").read_text(), "project\n")


if __name__ == "__main__":
    unittest.main()
