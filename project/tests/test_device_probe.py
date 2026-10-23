# SPDX-License-Identifier: MIT
"""D03 host fixtures and a disposable host-kernel helper; no device tested."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import stat
import time
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import device_probe as probe

BOOT = "45815f4e-fc06-4cf5-9bf6-d9d748173551"


class DeviceProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="device-probe-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root, self.card = self.base / "root", self.base / "card"
        self.root.mkdir()
        self.card.mkdir()
        self.tree = probe.InstalledTree(self.root, self.card)

    def put(self, name, contents):
        path = self.root / name.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
        return path

    def fixture(self, model="TrimUI Smart Pro TG5040"):
        self.put("/proc/device-tree/model", model + "\0")
        self.put("/proc/sys/kernel/random/boot_id", BOOT + "\n")
        self.put("/proc/123/stat", "123 (game (private title)) S " + " ".join(["0"] * 18) + " 999 0\n")
        self.put("/proc/mounts", "/dev/mmcblk0p1 /mnt/SDCARD vfat rw,uid=1000,secret=PRIVATE 0 0\n/dev/root / ext4 ro,errors=remount-ro 0 0\n//PASSWORD@HOST/private /home/owner nfs rw,password=PRIVATE 0 0\n")
        self.put("/etc/version", "TrimUI 1.0.4\n")
        self.put("/usr/bin/python3", b"offline must never execute")
        self.put("/usr/bin/readelf", b"offline must never execute readelf")

    def collect(self, **kwargs):
        return probe.collect(self.root, self.card, **kwargs)

    def test_static_inventory_is_explicitly_not_live_or_qualified(self):
        self.fixture()
        with patch.object(probe, "run_bounded") as command:
            report = self.collect(pid=123)
        command.assert_not_called()
        self.assertEqual(report["model_candidate"], "original-tg5040-candidate")
        self.assertEqual(report["firmware_observations"], [{"path": "/etc/version", "version": "1.0.4"}])
        self.assertEqual(report["boot_id"], BOOT)
        self.assertEqual(report["process_identity"], {"pid": 123, "starttime_ticks": 999})
        self.assertFalse(report["live_collector_root"])
        for key in ("hardware_qualified", "runtime_verified", "physical_restore_tested", "automatic_activation"):
            self.assertIs(report[key], False)
        self.assertIsNone(report["kernel_helper"])
        self.assertIn("copied filesystem", report["provenance"])
        self.assertEqual(report["tools"]["python"]["sha256"], hashlib.sha256(b"offline must never execute").hexdigest())
        self.assertIsNone(report["tools"]["python"]["version"])

    def test_sensitive_process_environment_maps_and_mount_options_are_absent(self):
        self.fixture()
        self.put("/proc/123/cmdline", b"SECRET PRIVATE_ROM.iso")
        self.put("/proc/123/environ", b"PASSWORD=PRIVATE")
        self.put("/proc/cpuinfo", "Hardware: TG5040\nSerial: PRIVATE-SERIAL\n")
        self.put("/etc/wpa_supplicant.conf", "psk=PRIVATE")
        report = self.collect(pid=123)
        output = json.dumps(report)
        for value in ("PRIVATE", "PASSWORD", "owner", "game (private title)"):
            self.assertNotIn(value, output)
        self.assertEqual(report["filesystems"], [{"mountpoint": "/mnt/SDCARD", "filesystem": "vfat", "flags": ["rw"]},
                                                  {"mountpoint": "/", "filesystem": "ext4", "flags": ["ro"]}])

    def test_unknown_model_and_newer_devices_remain_unknown(self):
        for model in ("generic ARM", "TrimUI Smart Pro S", "TrimUI Brick TG5040"):
            self.fixture(model)
            with self.subTest(model=model):
                self.assertIsNone(self.collect()["model_candidate"])

    def test_firmware_conflicts_are_retained_not_resolved_by_guess(self):
        self.fixture()
        self.put("/etc/trimui_version", "firmware=1.1.1")
        self.put("/etc/os-release", "firmware=9.9.9 password=SECRET")
        self.assertEqual([x["version"] for x in self.collect()["firmware_observations"]], ["1.0.4", "1.1.1"])

    def test_offline_tool_or_kernel_execution_is_refused(self):
        for kwargs in ({"kernel_probe": True}, {"tool_versions": True}):
            with self.subTest(kwargs=kwargs), patch.object(probe, "run_bounded") as run:
                with self.assertRaises(ValueError):
                    self.collect(**kwargs)
                run.assert_not_called()

    def test_missing_tools_and_boot_identity_remain_unavailable(self):
        report = self.collect()
        self.assertIsNone(report["boot_id"])
        self.assertEqual(report["tools"], {"python": None, "readelf": None})
        self.assertEqual({x["observation"] for x in report["errors"]}, {"boot_identity", "tool:python", "tool:readelf"})

    def test_malformed_oversized_and_nonregular_metadata_are_refused(self):
        self.fixture()
        boot = self.put("/proc/sys/kernel/random/boot_id", "not-a-uuid")
        self.assertIsNone(self.collect()["boot_id"])
        boot.write_bytes(b"x" * (probe.MAX_TEXT + 1))
        with self.assertRaises(ValueError):
            probe.read_text(self.tree, "/proc/sys/kernel/random/boot_id")
        boot.unlink()
        os.mkfifo(boot)
        with self.assertRaises(ValueError):
            probe.read_text(self.tree, "/proc/sys/kernel/random/boot_id")

    def test_dead_malformed_and_invalid_pid_are_refused(self):
        self.fixture()
        for value in (0, -1, True, 2**31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.process_identity(self.tree, value)
        for contents in ("123 (dead) Z " + " ".join(["0"] * 18) + " 999", "999 (wrong) S 1", "not a stat file"):
            self.put("/proc/123/stat", contents)
            self.assertIsNone(self.collect(pid=123)["process_identity"])

    def test_process_reuse_and_boot_changes_during_collection_are_rejected(self):
        self.fixture()
        real_tool = probe.tool_identity
        def change(*args, **kwargs):
            result = real_tool(*args, **kwargs)
            self.put("/proc/123/stat", "123 (changed) S " + " ".join(["0"] * 18) + " 1000 0\n")
            self.put("/proc/sys/kernel/random/boot_id", "42af80a8-595b-4a9f-a335-c640d9b166bf\n")
            return result
        with patch.object(probe, "tool_identity", side_effect=change):
            report = self.collect(pid=123)
        self.assertIsNone(report["process_identity"])
        self.assertIsNone(report["boot_id"])
        self.assertEqual(sum(x["reason"] == "changed_during_collection" for x in report["errors"]), 2)

    def test_symlink_escape_and_directory_replacement_cannot_read_host_files(self):
        self.fixture()
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "python3").write_bytes(b"HOST_SECRET")
        target = self.root / "usr/bin"
        original_resolve = self.tree.resolve
        def swap(name):
            result = original_resolve(name)
            target.rename(self.root / "usr/bin-old")
            target.symlink_to(outside)
            return result
        with patch.object(self.tree, "resolve", side_effect=swap), self.assertRaises(OSError):
            probe.tool_identity(self.tree, "/usr/bin/python3")
        with self.assertRaises((ValueError, OSError)):
            probe.tool_identity(self.tree, "/usr/bin/python3")

    def test_tool_path_replacement_after_hash_is_rejected(self):
        path = self.put("/usr/bin/python3", b"original tool")
        live_tree = probe.InstalledTree("/", self.card)
        def replace(*args, **kwargs):
            path.rename(path.with_name("old-python"))
            path.write_bytes(b"new tool")
            return b"Python 3.12.0\n"
        with patch.object(probe, "run_bounded", side_effect=replace), self.assertRaises(ValueError):
            probe.tool_identity(live_tree, str(path), execute_version=True)

    def test_low_level_version_api_cannot_execute_an_offline_tool(self):
        self.fixture()
        with patch.object(probe, "run_bounded") as run, self.assertRaises(ValueError):
            probe.tool_identity(self.tree, "/usr/bin/python3", execute_version=True)
        run.assert_not_called()

    def test_oversized_tool_is_refused_before_version_execution(self):
        path = self.put("/usr/bin/python3", b"x")
        with path.open("wb") as stream:
            stream.truncate(probe.MAX_TOOL + 1)
        with patch.object(probe, "run_bounded") as run, self.assertRaises(ValueError):
            probe.tool_identity(self.tree, "/usr/bin/python3", execute_version=True)
        run.assert_not_called()

    def test_tool_mutation_during_version_observation_is_rejected(self):
        path = self.put("/usr/bin/python3", b"original tool")
        def version(*args, **kwargs):
            path.write_bytes(b"changed tool!")
            return b"Python 3.12.0\n"
        live_tree = probe.InstalledTree("/", self.card)
        with patch.object(probe, "run_bounded", side_effect=version), self.assertRaises(ValueError):
            probe.tool_identity(live_tree, str(path), execute_version=True)

    def test_completed_disposable_command_never_signals_a_reaped_group(self):
        with patch.object(probe.os, "killpg") as kill:
            self.assertEqual(probe.run_bounded([sys.executable, "-c", "print('done')"]), b"done\n")
            kill.assert_not_called()
        with patch.object(probe.os, "killpg") as kill:
            with self.assertRaises(ValueError):
                probe.run_bounded([sys.executable, "-c", "raise SystemExit(3)"])
            kill.assert_not_called()

    def test_timed_out_disposable_command_is_cleaned_before_wait_reaps_root(self):
        real_kill = os.killpg
        seen = []
        def kill(pid, sig):
            # WNOWAIT observes without releasing the root identity. A live
            # child returns None; a zombie is still owned and cannot be reused.
            observation = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            seen.append((pid, observation))
            return real_kill(pid, sig)
        with patch.object(probe.os, "killpg", side_effect=kill):
            with self.assertRaises(ValueError):
                probe.run_bounded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=.1)
        self.assertEqual(len(seen), 1)

    def test_closed_output_pipes_do_not_escape_deadline_normalization(self):
        script = "import os,time; os.close(1); os.close(2); time.sleep(30)"
        started = time.monotonic()
        with self.assertRaises(ValueError):
            probe.run_bounded([sys.executable, "-c", script], timeout=.1)
        self.assertLess(time.monotonic() - started, 3)
        self.fixture()
        with patch.object(probe, "observe_kernel", side_effect=ValueError("deadline")):
            report = probe.collect("/", self.card, kernel_probe=True)
        self.assertIsNone(report["kernel_helper"])
        self.assertIn({"observation": "kernel_helper", "reason": "ValueError"}, report["errors"])

    def test_disposable_command_is_bounded_by_output_and_deadline(self):
        for script, kwargs in (("print('x' * 10000)", {"limit": 100}), ("import time; time.sleep(30)", {"timeout": .1})):
            started = time.monotonic()
            with self.subTest(script=script), self.assertRaises(ValueError):
                probe.run_bounded([sys.executable, "-c", script], **kwargs)
            self.assertLess(time.monotonic() - started, 3)

    @unittest.skipUnless(sys.platform.startswith("linux"), "live host tool execution only")
    def test_explicit_trusted_host_python_version_uses_same_descriptor(self):
        tree = probe.InstalledTree("/", self.card)
        report = probe.tool_identity(tree, sys.executable, execute_version=True)
        self.assertTrue(report["version"].startswith("Python "))
        self.assertTrue(report["version_executed"])
        self.assertEqual(report["sha256"], hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())

    def test_helper_provenance_binds_actual_inputs_not_configured_python_tool(self):
        configured = self.put("/trusted/configured-python", b"a different inventoried Python")
        report = probe.collect("/", self.card, python_path=str(configured), readelf_path=sys.executable,
                               kernel_probe=True)
        helper = report["kernel_helper"]
        self.assertIsNotNone(helper)
        self.assertEqual(report["tools"]["python"]["sha256"], hashlib.sha256(configured.read_bytes()).hexdigest())
        self.assertEqual(helper["interpreter"]["sha256"], hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())
        self.assertNotEqual(helper["interpreter"]["sha256"], report["tools"]["python"]["sha256"])
        self.assertEqual(helper["source"]["sha256"], hashlib.sha256(Path(probe.__file__).read_bytes()).hexdigest())
        self.assertFalse(report["hardware_qualified"])

    def test_helper_execution_uses_opened_inputs_and_rejects_path_replacement(self):
        source = self.base / "probe-source.py"
        source.write_bytes(Path(probe.__file__).read_bytes())
        capabilities = {"subreaper_adoption_wait": "supported", "sealed_memfd_inherited_read": "supported",
                        "unix_peer_credentials": "supported"}
        def swapped(argv, **kwargs):
            self.assertTrue(argv[0].startswith("/proc/self/fd/"))
            self.assertTrue(argv[1].startswith("/proc/self/fd/"))
            self.assertEqual({int(argv[0].rpartition("/")[2]), int(argv[1].rpartition("/")[2])}, set(kwargs["pass_fds"]))
            source.rename(self.base / "probe-source-old.py")
            source.write_bytes(b"changed source")
            return json.dumps(capabilities).encode()
        with patch.object(probe, "__file__", str(source)), patch.object(probe, "run_bounded", side_effect=swapped):
            with self.assertRaises(ValueError):
                probe.observe_kernel()

    def test_helper_unavailability_is_retained_and_invalid_shape_refused(self):
        unavailable = {"subreaper_adoption_wait": "unavailable:OSError", "sealed_memfd_inherited_read": "supported",
                       "unix_peer_credentials": "unavailable:AttributeError"}
        with patch.object(probe, "run_bounded", return_value=json.dumps(unavailable).encode()):
            self.assertEqual(probe.observe_kernel()["capabilities"], unavailable)
        for raw in (b'[]', b'{"injected":"qualified"}', b'not json'):
            with self.subTest(raw=raw), patch.object(probe, "run_bounded", return_value=raw), self.assertRaises(ValueError):
                probe.observe_kernel()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux disposable helper only")
    def test_real_host_kernel_helper_is_fresh_and_does_not_qualify_device(self):
        execution = probe.observe_kernel()
        value = execution["capabilities"]
        self.assertEqual(set(value), {"subreaper_adoption_wait", "sealed_memfd_inherited_read", "unix_peer_credentials"})
        self.assertTrue(all(x == "supported" or x.startswith("unavailable:") for x in value.values()))
        self.assertEqual(execution["interpreter"]["sha256"], hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest())
        self.assertEqual(execution["source"]["sha256"], hashlib.sha256(Path(probe.__file__).read_bytes()).hexdigest())
        self.assertFalse(self.collect()["hardware_qualified"])

    def test_cli_writes_exclusive_durable_output_only_outside_inputs(self):
        self.fixture()
        output = self.base / "probe.json"
        argv = ["--root", str(self.root), "--sd-root", str(self.card), "--pid", "123", "--output", str(output)]
        self.assertEqual(probe.main(argv), 0)
        original = output.read_bytes()
        self.assertEqual(probe.main(argv), 2)
        self.assertEqual(output.read_bytes(), original)
        for output in (self.root / "output.json", self.card / "output.json"):
            argv[-1] = str(output)
            self.assertEqual(probe.main(argv), 2)
            self.assertFalse(output.exists())

    def test_failed_directory_sync_does_not_publish_a_success_receipt(self):
        self.fixture()
        output = self.base / "probe.json"
        real_fsync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("full report filesystem")
            return real_fsync(fd)
        with patch("recovery_preflight.os.fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                probe.write_report(output, self.collect(), [self.root, self.card])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
