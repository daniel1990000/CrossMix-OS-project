# SPDX-License-Identifier: MIT
"""Certify the complete host check against untouched, pinned source checkouts.

Individual unittest invocations remain useful for development. Only this full
runner produces a certification record; no skips or expected failures are allowed.
"""
from __future__ import annotations

import argparse
import compileall
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent


def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix="." + path.name, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def git(source, *arguments):
    try:
        return subprocess.run(["git", "-C", str(source), *arguments],
                              check=True, capture_output=True, text=True).stdout.rstrip("\n")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Cannot read the required Git source checkout: " + str(source)) from error


def verify_checkout(source, expected_commit, required_files, tree=None):
    source = Path(source).resolve(strict=True)
    if not source.is_dir() or Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("Source root must be the Git checkout root: " + str(source))
    actual = git(source, "rev-parse", "HEAD")
    if actual != expected_commit:
        raise ValueError("Source commit differs: " + str(source) + " (expected " +
                         expected_commit + ", observed " + actual + ")")
    changed = git(source, "diff", "--no-ext-diff", "--name-only", "HEAD", "--")
    if changed:
        raise ValueError("Source checkout has changed tracked files: " + str(source))
    if git(source, "ls-files", "--others", "--exclude-standard"):
        raise ValueError("Source checkout has untracked files: " + str(source))
    materialized = 0
    # Compare actual bytes to HEAD, including files hidden from diff by local
    # assume-unchanged/skip-worktree flags. Sparse-excluded files may be absent;
    # consumed inputs below and the source tests must still be present.
    for entry in git(source, "ls-tree", "-r", "-z", "--full-tree", "HEAD").split("\0"):
        if not entry:
            continue
        metadata, relative = entry.split("\t", 1)
        mode, kind, object_id = metadata.split()
        path = source / relative
        if kind != "blob" or (not path.exists() and not path.is_symlink()):
            continue
        if mode == "120000" and path.is_symlink():
            data = os.fsencode(os.readlink(path))
        elif mode in ("100644", "100755") and path.is_file() and not path.is_symlink():
            data = path.read_bytes()
        else:
            raise ValueError("Materialized source file type differs: " + str(path))
        observed = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if observed != object_id:
            raise ValueError("Materialized source file differs from Git HEAD: " + str(path))
        materialized += 1
    for relative, expected_hash in required_files.items():
        path = source / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("Required source file is missing or not regular: " + str(path))
        if expected_hash and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Required source file differs from its lock: " + str(path))
    record = {"root": str(source), "expected_commit": expected_commit,
              "observed_commit": actual, "tracked_content_clean": True,
              "required_files_checked": len(required_files),
              "materialized_files_checked": materialized}
    if tree:
        relative, expected_tree = tree
        actual_tree = git(source, "rev-parse", "HEAD:" + relative)
        if actual_tree != expected_tree:
            raise ValueError("Pinned source subtree differs: " + relative)
        record["subtree"] = {"path": relative, "expected": expected_tree, "observed": actual_tree}
    return record


def source_specs(project=PROJECT):
    spruce_lock = project.parent / "docs/spruce-source-lock.json"
    ppsspp_lock = project / "ppsspp/source-lock.json"
    ra_lock = project / "retroarch/source-lock.json"
    ports_lock = project / "ports/celeste-fix.lock.json"
    portmaster_lock = project / "profiles/ports-sources.lock.json"
    spruce = json.loads(spruce_lock.read_text())
    ppsspp = json.loads(ppsspp_lock.read_text())
    ra = json.loads(ra_lock.read_text())
    ports = json.loads(ports_lock.read_text())
    portmaster = json.loads(portmaster_lock.read_text())["portmaster_gui_sources"]
    return [
        ("SPRUCE_SOURCE_ROOT", spruce_lock, spruce["base"]["source_commit"],
         {path: None for path in ("App/PyUI/main-ui/mainui.py", "App/PyUI/main-ui/LICENSE.md",
                                  "App/PyUI/LICENSE.md", "App/PyUI/launch.sh",
                                  "spruce/scripts/principal.sh", "spruce/scripts/runtime.sh")},
         (spruce["base"]["pyui_source_path"], spruce["base"]["pyui_git_tree"])),
        ("PPSSPP_SOURCE_ROOT", ppsspp_lock, ppsspp["upstream"]["commit"],
         {**{item["path"]: item["sha256"] for item in ppsspp["source_files"]},
          ppsspp["upstream"]["license_source"]: ppsspp["upstream"]["license_sha256"]}, None),
        ("SPRUCE_RA_SOURCE_ROOT", ra_lock, ra["recipe"]["commit"],
         {item["path"]: item["sha256"] for item in ra["inputs"]}, None),
        ("PORTS_SOURCE_ROOT", ports_lock, ports["commit"],
         {item["path"]: item["base_sha256"] for item in ports["files"]}, None),
        ("PORTMASTER_SOURCE_ROOT", portmaster_lock, portmaster[0]["commit"],
         {item["path"]: item["sha256"] for item in portmaster}, None),
    ]


def verify_sources(environment, records, project=PROJECT):
    for variable, lock, commit, files, tree in source_specs(project):
        value = environment.get(variable)
        if not value:
            raise ValueError("Certification requires explicit " + variable + " at its pinned Git checkout")
        record = {"environment_variable": variable, "lock": str(lock.relative_to(project.parent)),
                  "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}
        records.append(record)
        record.update(verify_checkout(value, commit, files, tree))


class CertificationResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.passed = 0

    def addSuccess(self, test):
        self.passed += 1
        super().addSuccess(test)

    def wasSuccessful(self):
        return (super().wasSuccessful() and self.testsRun > 0 and
                not self.skipped and not self.expectedFailures)


def run_suite(directory, output):
    directory = Path(directory)
    report = {"directory": str(directory), "successful": False}
    try:
        if not directory.is_dir():
            raise ValueError("Required test suite is missing: " + str(directory))
        suite = unittest.TestLoader().discover(str(directory))
        result = unittest.TextTestRunner(verbosity=2, resultclass=CertificationResult).run(suite)
        report.update({"successful": result.wasSuccessful(), "tests_run": result.testsRun,
                       "passed": result.passed, "failures": len(result.failures),
                       "errors": len(result.errors), "skipped": len(result.skipped),
                       "expected_failures": len(result.expectedFailures),
                       "unexpected_successes": len(result.unexpectedSuccesses),
                       "skip_details": [{"test": test.id(), "reason": reason}
                                        for test, reason in result.skipped]})
        if not report["successful"]:
            print("Certification rejected this suite: all discovered tests must pass; "
                  "empty suites, skips and expected failures are not accepted.", file=sys.stderr)
    except Exception as error:
        report["error"] = str(error)
        print("Certification suite error: " + str(error), file=sys.stderr)
    write_report(output, report)
    return 0 if report["successful"] else 1


def certify(report_path):
    report = {"schema": 1, "kind": "pinned-source-host-certification",
              "started_at": datetime.now(timezone.utc).isoformat(), "successful": False,
              "sources": [], "suites": [], "preview_passed": False,
              "device_qualified": False}
    try:
        report["phase"] = "source-preflight"
        verify_sources(os.environ, report["sources"])
        report["phase"] = "compile"
        for name in ("psp_shell", "bridge", "integration", "tools", "packaging", "retroarch", "dev"):
            if not compileall.compile_dir(PROJECT / name, quiet=1):
                raise ValueError("Python compilation failed in " + name)
        report["phase"] = "tests"
        with tempfile.TemporaryDirectory(prefix="smartpro-certification-") as temporary:
            for index, directory in enumerate((PROJECT / "tests", PROJECT / "ppsspp/tests")):
                suite_report = Path(temporary) / (str(index) + ".json")
                process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                          "--test-directory", str(directory),
                                          "--test-report", str(suite_report)], cwd=REPOSITORY)
                if suite_report.is_file():
                    entry = json.loads(suite_report.read_text())
                else:
                    entry = {"directory": str(directory), "successful": False,
                             "error": "Test process did not produce a result record"}
                entry["process_exit_code"] = process.returncode
                report["suites"].append(entry)
        keys = ("tests_run", "passed", "failures", "errors", "skipped",
                "expected_failures", "unexpected_successes")
        report["totals"] = {key: sum(entry.get(key, 0) for entry in report["suites"]) for key in keys}
        if not all(entry["successful"] and entry["process_exit_code"] == 0 for entry in report["suites"]):
            raise ValueError("One or more required suites failed certification")
        report["phase"] = "source-recheck"
        report["sources_after_tests"] = []
        verify_sources(os.environ, report["sources_after_tests"])
        report["phase"] = "preview"
        subprocess.run([sys.executable, "-m", "psp_shell", "--demo", "--headless", "--frames", "2",
                        "--screen", "library", "--screenshot", str(REPOSITORY / "dist/library.png"),
                        "--report", str(REPOSITORY / "dist/host-preview.json")], cwd=REPOSITORY, check=True)
        report["preview_passed"] = True
        report["phase"] = "complete"
        report["successful"] = True
    except Exception as error:
        report["error"] = str(error)
        print("Host certification failed: " + str(error), file=sys.stderr)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_report(report_path, report)
        print("Host certification record: " + str(report_path), file=sys.stderr)
    return 0 if report["successful"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPOSITORY / "dist/certification.json")
    parser.add_argument("--test-directory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--test-report", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.test_directory is not None:
        if arguments.test_report is None:
            parser.error("--test-directory requires --test-report")
        return run_suite(arguments.test_directory, arguments.test_report)
    return certify(arguments.report)


if __name__ == "__main__":
    raise SystemExit(main())
