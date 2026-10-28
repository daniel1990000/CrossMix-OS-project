# SPDX-License-Identifier: MIT
"""Actual SDL virtual axes/buttons, stale commands and PID-bound publication."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

DEV = Path(__file__).resolve().parents[1] / "dev"
spec = importlib.util.spec_from_file_location("host_virtual_controller", DEV / "host_virtual_controller.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class HostVirtualControllerTests(unittest.TestCase):
    def test_wrong_executable_and_changed_digest_preserve_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = root / "command"
            command.write_text("prior\n")
            command.chmod(0o600)
            exe = Path(sys.executable).resolve()
            ticks = int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])
            args = dict(pid=os.getpid(), expected_start_ticks=ticks, executable=exe, sha256="0" * 64, command=command,
                        record=root / "requests.jsonl", axes=[0, 0, 0, 0], buttons=0, seconds=.1)
            with self.assertRaisesRegex(ValueError, "digest"):
                controller.send(**args)
            args["executable"] = Path("/bin/sh").resolve()
            with self.assertRaisesRegex(ValueError, "executable"):
                controller.send(**args)
            args["executable"] = exe
            args["sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
            args["expected_start_ticks"] = ticks + 1
            with self.assertRaisesRegex(ValueError, "start ticks"):
                controller.send(**args)
            self.assertEqual(command.read_text(), "prior\n")
            self.assertFalse(args["record"].exists())

    def test_command_log_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = root / "command"
            command.write_text("original")
            command.chmod(0o600)
            alias = root / "hardlink"
            os.link(command, alias)
            for record in (root / "unused" / ".." / "command", alias):
                with self.assertRaisesRegex(ValueError, "must differ"):
                    controller.send(pid=os.getpid(), expected_start_ticks=0,
                                    executable=Path(sys.executable), sha256="0" * 64,
                                    command=command, record=record, axes=[0] * 4,
                                    buttons=0, seconds=.1)
            self.assertEqual(command.read_text(), "original")

    def test_actual_sdl_analogue_buttons_expiry_and_wrong_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "controller.so"
            subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                            str(DEV / "host_virtual_controller.c"), "-ldl", "-o", str(library)], check=True)
            executable = Path(sys.executable).resolve()
            script = root / "probe.py"
            script.write_text('''import ctypes, importlib.util, json, os, pathlib, sys, time
root=pathlib.Path(sys.argv[1]);dev=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location("controller",dev/"host_virtual_controller.py")
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
s=ctypes.CDLL("libSDL2-2.0.so.0",mode=ctypes.RTLD_GLOBAL)
assert s.SDL_Init(0x2200)==0
hook=ctypes.CDLL(None);hook.SDL_PollEvent.argtypes=[ctypes.c_void_p];event=ctypes.create_string_buffer(128)
def pump():
 for _ in range(8):hook.SDL_PollEvent(event)
pump();assert s.SDL_NumJoysticks()==1
s.SDL_JoystickOpen.restype=ctypes.c_void_p;stick=s.SDL_JoystickOpen(0)
s.SDL_JoystickGetAxis.argtypes=[ctypes.c_void_p,ctypes.c_int];s.SDL_JoystickGetAxis.restype=ctypes.c_int16
s.SDL_JoystickGetButton.argtypes=[ctypes.c_void_p,ctypes.c_int];s.SDL_JoystickGetButton.restype=ctypes.c_uint8
command=root/"command";record=root/"requests.jsonl";exe=pathlib.Path(sys.executable).resolve()
import hashlib
sha=hashlib.sha256(exe.read_bytes()).hexdigest()
ticks=int(pathlib.Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19])
r=c.send(pid=os.getpid(),expected_start_ticks=ticks,executable=exe,sha256=sha,command=command,record=record,axes=[1,-.5,0,.25],buttons=1,seconds=.1)
pump();assert [s.SDL_JoystickGetAxis(stick,i) for i in range(4)]==[32767,-16384,0,8192]
assert s.SDL_JoystickGetButton(stick,0)==1
time.sleep(.12);pump()
assert all(s.SDL_JoystickGetAxis(stick,i)==0 for i in range(6))
assert all(s.SDL_JoystickGetButton(stick,i)==0 for i in range(15))
# Fresh higher-sequence command for another PID must never inject movement.
parts=command.read_text().split();parts[0]="5";parts[1]=str(os.getpid()+100000)
parts[3]=str(time.monotonic_ns());parts[4]=str(time.monotonic_ns()+100000000)
command.write_text(" ".join(parts));pump()
assert s.SDL_JoystickGetAxis(stick,0)==0
# A correctly bound but late packet is retained and neutralized.
parts[0]="6";parts[1]=str(os.getpid());parts[3]="1";parts[4]="2"
command.write_text(" ".join(parts));pump()
assert s.SDL_JoystickGetAxis(stick,0)==0
hook.SDL_Quit()
''')
            env = dict(os.environ, LD_PRELOAD=str(library), TRIMUI_CONTROLLER_EXECUTABLE=str(executable),
                       TRIMUI_CONTROLLER_COMMAND=str(root / "command"),
                       TRIMUI_CONTROLLER_LOG=str(root / "observed.jsonl"), SDL_AUDIODRIVER="dummy")
            subprocess.run([sys.executable, str(script), str(root), str(DEV)], env=env, check=True,
                           timeout=20, capture_output=True, text=True)
            observations = [json.loads(line) for line in (root / "observed.jsonl").read_text().splitlines()]
            events = [row["event"] for row in observations]
            for expected in ("attached", "applied", "deadline_neutral", "invalid_neutral",
                             "expired_command", "quit_neutral"):
                self.assertIn(expected, events)
            applied = next(row for row in observations if row["event"] == "applied")
            self.assertGreaterEqual(applied["observed_monotonic_ns"], applied["requested_monotonic_ns"])
            self.assertLess(applied["observed_monotonic_ns"], applied["expires_monotonic_ns"])
            self.assertTrue(all(row["result"] >= 0 for row in observations if row["event"] != "expired_command"))


if __name__ == "__main__":
    unittest.main()
