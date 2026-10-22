# Installed loader and library evidence

`project/tools/installed_runtime.py` inspects the installed emulator with host
`readelf`. It records its exact SHA-256, size, ELF machine, interpreter, dynamic
dependencies and required symbol versions. The interpreter is read at its exact
installed path. Library paths must be supplied explicitly or observed in an
already-running process's mappings. The probe never runs an emulator, loader,
`ldd`, launcher or hardware command.

Run it on the original device only if Python 3 and a trusted `readelf` are already
available. This command observes the current emulator; it does not start one:

```sh
python3 project/tools/installed_runtime.py --pid EXISTING_PPSSPP_PID --output /tmp/ppsspp-installed-runtime.json
```

Select the PID using the existing device operator's process inventory. The probe
requires `/proc/PID/exe` to identify the exact selected emulator and requires it
in the process maps. It compares process start time, executable link and maps
before and after collection. On the live root, each mapped library's device and
inode must match the object being hashed. Process arguments, environment,
memory, mapped ROM names and save contents are excluded. A deleted mapped
engine/library, PID reuse, changing maps or unreadable object prevents reliable
evidence. Raw process maps are not exported.

For an existing mounted filesystem copy, keep its original absolute paths in
the virtual root and provide the separate card location:

```sh
python3 project/tools/installed_runtime.py --root /path/to/rootfs-copy --sd-root /path/to/card-copy --library /lib/libc.so.6 --library /usr/lib/libSDL2-2.0.so.0 --output /tmp/ppsspp-copied-runtime.json
```

`/mnt/SDCARD` maps to `--sd-root`. Absolute symlinks refer to the inspected root,
including symlinks crossing into that card mount. They never fall back to host
libraries. Copied `/proc` evidence can be inspected with `--pid`, but its inode
numbers cannot be matched to host copies and the report leaves those checks
unknown. Snapshot evidence cannot qualify the live runtime.

Every dependency check retains its supplied candidates. Missing libraries,
missing versions and multiple matching identities are reported without choosing
an arbitrary path. Search tags are recorded without pretending to reproduce
the installed loader's search order. Mapped PowerVR/EGL/GLES libraries provide
identities only; successful rendering remains a separate physical test.

Output must be a new explicit file. A zero exit status means the report was
written; inspect `errors` and `dependency_checks` for incomplete evidence. All
reports keep `physical_qualification=false` and `resume_qualified=false`. This
probe cannot establish input mappings, complete config-writer ownership, save
completion, child-process termination or foreground-return authority. Collect
those separately on a spare/restorable card before changing any profile gate.

Host tests use filesystem/process fixtures and a real host ELF inspected with
`readelf`. No original-device observation is claimed.
