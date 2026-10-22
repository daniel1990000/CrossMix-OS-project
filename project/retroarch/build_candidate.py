#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a private, original-TG5040 RetroArch/IGM candidate without executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
LOCK = ROOT / "build-inputs.lock.json"
DOCKER_SELECTORS = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
SDK_LINK = ("# SPDX-License-Identifier: MIT\n"
            "# The recipe adds -lstdc++ explicitly; keep the proved GCC9 runtime.\n"
            "LIBS := $(patsubst -lstdc++,/usr/lib/gcc-cross/aarch64-linux-gnu/9/libstdc++.a,$(LIBS))\n"
            "LDFLAGS += -static-libstdc++ -Wl,-t\n")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def load_lock() -> dict:
    lock = json.loads(LOCK.read_text())
    if lock.get("schema") != 1 or not re.fullmatch(r"sha256:[0-9a-f]{64}", lock["toolchain"]["image_id"]):
        raise ValueError("An immutable compiler image and supported input lock are required")
    for item in lock["helpers"]:
        verify_file(PROJECT, item)
    verify_file(ROOT, lock["extension"])
    return lock


def verify_file(directory: Path, item: dict) -> Path:
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe input path")
    path = directory / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Missing or redirected locked input: " + str(relative))
    if sha(path) != item["sha256"]:
        raise ValueError("Locked input hash differs: " + str(relative))
    return path


def verify_checkout(path: Path, commit: str, tree: str | None = None) -> None:
    if run(["git", "-C", str(path), "rev-parse", "HEAD"]) != commit:
        raise ValueError("Source commit differs: " + str(path))
    if tree and run(["git", "-C", str(path), "rev-parse", "HEAD^{tree}"]) != tree:
        raise ValueError("Source tree differs")
    if run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all", "--ignored=matching"]):
        raise ValueError("Source checkout must be pristine, including ignored files")
    entries = run(["git", "-C", str(path), "ls-files", "-t"]).splitlines()
    if any(line.startswith("S ") for line in entries):
        raise ValueError("Full checkout required; sparse source is incomplete")


def recipe_options(text: str) -> tuple[list[str], dict[str, str]]:
    """Extract a fixed configure command and flag suffixes; never evaluate shell."""
    matches = re.findall(r"^\./configure (.+?)(?:\n\n|\Z)", text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError("Expected one fixed recipe configure command")
    joined = matches[0].replace("\\\n", " ")
    args = shlex.split(joined)
    if not args or any(not re.fullmatch(r"--[a-z0-9-]+(?:=[a-z0-9_.-]+)?", arg) for arg in args):
        raise ValueError("Recipe configure arguments are not fixed literals")
    if args.count("--enable-vulkan") != 1:
        raise ValueError("Expected universal recipe Vulkan selection")
    # Original TG5040 SDK has EGL/GLES, no Vulkan loader. No foreign driver is added.
    args[args.index("--enable-vulkan")] = "--disable-vulkan"
    flags = {}
    for key in ("CFLAGS", "CXXFLAGS", "LDFLAGS"):
        values = re.findall(r'^export ' + key + r'="\$' + key + r' ([^"\n]+)"$', text, re.M)
        if len(values) != 1 or re.search(r"[$`\n]", values[0]):
            raise ValueError("Recipe compiler flags changed: " + key)
        flags[key] = values[0]
    return args, flags


def compiler_environment(recipe: str) -> tuple[list[str], dict[str, str]]:
    import sys
    sys.path.insert(0, str(PROJECT / "ppsspp"))
    from sdk_search import include_flags, link_flags
    args, flags = recipe_options(recipe)
    def headers(cxx: bool) -> str:
        # Engine-local compatibility headers must precede SDK system headers.
        # -nostdinc still forbids the compiler's Ubuntu C header defaults.
        values = include_flags(cxx)
        index = values.index("-I/opt/sysroot/usr/include")
        values[index:index + 1] = ["-isystem", "/opt/sysroot/usr/include"]
        return shlex.join(values)
    env = {
        "CC": "aarch64-linux-gnu-gcc --sysroot=/opt/sysroot",
        "CXX": "aarch64-linux-gnu-g++ --sysroot=/opt/sysroot",
        "AR": "aarch64-linux-gnu-ar", "STRIP": "aarch64-linux-gnu-strip",
        "PKG_CONF_PATH": "/usr/bin/pkg-config",  # RetroArch's cross-tool selector
        "PKG_CONFIG_SYSROOT_DIR": "/opt/sysroot", "PKG_CONFIG_PATH": "",
        "PKG_CONFIG_LIBDIR": "/opt/sysroot/usr/lib/pkgconfig:/opt/sysroot/usr/share/pkgconfig",
        "CFLAGS": headers(False) + " " + flags["CFLAGS"],
        "CXXFLAGS": headers(True) + " " + flags["CXXFLAGS"],
        "LDFLAGS": shlex.join(link_flags()) + " " + flags["LDFLAGS"],
    }
    return args, env


def source_inventory(directory: Path) -> list[dict]:
    result = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Source symlink escapes its retained tree: " + relative)
            result.append({"path": relative, "symlink": os.readlink(path)})
        elif path.is_file():
            result.append({"path": relative, "sha256": sha(path)})
    return result


def prepare(upstream: Path, recipe: Path, work: Path) -> dict:
    lock = load_lock()
    upstream, recipe, work = upstream.resolve(), recipe.resolve(), work.resolve()
    if work.exists() or any(work.is_relative_to(root) or root.is_relative_to(work)
                            for root in (upstream, recipe, PROJECT)):
        raise ValueError("Use a new, separate private work directory")
    verify_checkout(upstream, lock["upstream"]["commit"], lock["upstream"]["tree"])
    verify_checkout(recipe, lock["recipe"]["commit"])
    for item in lock["recipe"]["files"]:
        verify_file(recipe, item)
    expected_patches = [item["path"] for item in lock["recipe"]["files"] if item["path"].startswith("patches/common/")]
    if sorted(path.relative_to(recipe).as_posix() for path in (recipe / "patches/common").glob("*.patch")) != expected_patches:
        raise ValueError("Recipe common patch set differs")
    expected_shared = [item["path"] for item in lock["recipe"]["files"] if item["path"].startswith("common_src/")]
    if sorted(path.relative_to(recipe).as_posix() for path in (recipe / "common_src").iterdir()) != expected_shared:
        raise ValueError("Recipe shared-source set differs")
    args, env = compiler_environment((recipe / "build.sh").read_text())
    work.mkdir(mode=0o700, parents=True)
    source = work / "source"
    shutil.copytree(upstream, source, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    for name in expected_patches:
        run(["git", "apply", "--check", str(recipe / name)], cwd=source)
        run(["git", "apply", str(recipe / name)], cwd=source)
    for name in expected_shared:
        shutil.copy2(recipe / name, source / Path(name).name)
    patch = ROOT / lock["extension"]["path"]
    run(["git", "apply", "--check", str(patch)], cwd=source)
    run(["git", "apply", str(patch)], cwd=source)
    for item in lock["patched_source"]:
        verify_file(source, item)
    inventory = source_inventory(source)
    save(work / "prepared-sources.json", inventory)
    (work / "sdk-link.mk").write_text(SDK_LINK)
    shutil.copy2(LOCK, work / LOCK.name)
    helpers = work / "helpers"
    helpers.mkdir()
    for item in lock["helpers"]:
        shutil.copy2(PROJECT / item["path"], helpers / Path(item["path"]).name)
    record = {
        "schema": 1, "phase": "prepared", "lock_sha256": sha(LOCK),
        "upstream": str(upstream), "recipe": str(recipe), "work": str(work),
        "input_inventory_sha256": sha(work / "prepared-sources.json"),
        "source_file_count": len(inventory), "configure_args": args, "compiler_environment": env,
        "adaptations": ["Original TG5040: Vulkan disabled because the pinned SDK has no Vulkan loader", "Explicit GCC9/SDK headers, libraries and SDK-only pkg-config search", "SDK C headers use -isystem after engine-local -I compatibility headers, with -nostdinc retained", "Build-only Make overlay replaces explicit -lstdc++ with GCC9 static C++ runtime; final link trace retained"],
        "sdk_link_overlay_sha256": sha(work / "sdk-link.mk"),
        "target_executed": False, "device_compatibility_proved": False,
        "installed_emulators_changed": False, "distribution_cleared": False,
    }
    save(work / "build-manifest.json", record)
    # Preserve complete original and modified engine/recipe sources BEFORE configure.
    # No .git, session environment, SDK blobs, generated objects, or raw config logs.
    with tarfile.open(work / "source-inputs.tar.gz", "w:gz") as archive:
        def no_git(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
            return None if ".git" in Path(info.name).parts else info
        archive.add(upstream, arcname="upstream", filter=no_git)
        archive.add(source, arcname="modified", filter=no_git)
        archive.add(recipe, arcname="recipe", filter=no_git)
        for path in (ROOT / "build_candidate.py", LOCK, ROOT / "source-lock.json", ROOT / "build-candidate.md", PROJECT / "LICENSE", patch):
            archive.add(path, arcname="project/" + path.relative_to(PROJECT).as_posix())
        archive.add(helpers, arcname="project/build-helpers")
        archive.add(work / "prepared-sources.json", arcname="prepared-sources.json")
        archive.add(work / "sdk-link.mk", arcname="sdk-link.mk")
    record["source_inputs"] = {"name": "source-inputs.tar.gz", "size": (work / "source-inputs.tar.gz").stat().st_size, "sha256": sha(work / "source-inputs.tar.gz")}
    save(work / "build-manifest.json", record)
    return record


def validate_work(work: Path) -> tuple[dict, dict]:
    lock = load_lock()
    record = json.loads((work / "build-manifest.json").read_text())
    if record["lock_sha256"] != sha(LOCK) or sha(work / LOCK.name) != sha(LOCK):
        raise ValueError("Prepared build input lock differs")
    if record["input_inventory_sha256"] != sha(work / "prepared-sources.json"):
        raise ValueError("Prepared source inventory differs")
    if record["sdk_link_overlay_sha256"] != sha(work / "sdk-link.mk") or (work / "sdk-link.mk").read_text() != SDK_LINK:
        raise ValueError("Locked SDK link overlay differs")
    for item in json.loads((work / "prepared-sources.json").read_text()):
        if "symlink" in item:
            path = work / "source" / item["path"]
            if not path.is_symlink() or os.readlink(path) != item["symlink"]:
                raise ValueError("Prepared source link differs")
        else:
            verify_file(work / "source", item)
    for item in lock["helpers"]:
        verify_file(work / "helpers", {"path": Path(item["path"]).name, "sha256": item["sha256"]})
    return lock, record


def docker_command(work: Path, image_id: str, script: str) -> tuple[list[str], dict[str, str]]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Moving image tags are not accepted")
    path = work / "container-run.sh"
    path.write_text(script)
    env = dict(os.environ)
    for name in DOCKER_SELECTORS:
        env.pop(name, None)
    args = ["docker", "--host=unix:///var/run/docker.sock", "run", "--rm", "--network=none",
            "--user", str(os.getuid()) + ":" + str(os.getgid()), "--cpus=4", "--memory=8g",
            "--entrypoint", "/bin/sh", "--mount", "type=bind,src=" + str(work) + ",dst=/build",
            image_id, "/build/container-run.sh"]
    return args, env


def execute_container(work: Path, lock: dict, script: str, log_name: str) -> None:
    args, env = docker_command(work, lock["toolchain"]["image_id"], script)
    with (work / log_name).open("w") as output:
        subprocess.run(args, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def configure(work: Path) -> dict:
    lock, record = validate_work(work)
    script = "#!/bin/sh\nset -eu\numask 077\n"
    script += "python3 /build/helpers/sdk_search.py > /build/sdk-preflight.json\n"
    script += "dpkg-query -W > /build/compiler-packages.tsv\n"
    script += "aarch64-linux-gnu-gcc --version > /build/compiler-version.txt\ncd /build/source\n"
    script += "".join("export " + key + "=" + shlex.quote(value) + "\n" for key, value in record["compiler_environment"].items())
    script += "$CC $CFLAGS -Ilibretro-common/include/compat/zlib -Ilibretro-common/include -H -c deps/libz/adler32.c -o /build/vendor-header-probe.o 2> /build/vendor-header-probe.txt\n"
    script += "exec ./configure " + shlex.join(record["configure_args"]) + "\n"
    execute_container(work, lock, script, "configure-output.log")
    trace = (work / "vendor-header-probe.txt").read_text()
    if not re.search(r"^\.+ libretro-common/include/compat/zlib/zlib.h$", trace, re.M) or re.search(r"^\.+ /opt/sysroot/usr/include/zlib.h$", trace, re.M):
        raise ValueError("SDK headers displaced engine's vendored compatibility header")
    if re.search(r"^\.+ /usr/aarch64-linux-gnu/include/(?!c\+\+/)", trace, re.M):
        raise ValueError("Ubuntu C header leakage in engine source probe")
    config = work / "source/config.mk"
    features = dict(re.findall(r"^(HAVE_[A-Z0-9_]+)\s*=\s*([01])$", config.read_text(), re.M))
    required = ("HAVE_SDL2", "HAVE_EGL", "HAVE_OPENGLES", "HAVE_OPENGLES3", "HAVE_ALSA", "HAVE_UDEV", "HAVE_FREETYPE", "HAVE_NETWORKING", "HAVE_SSL")
    if any(features.get(name) != "1" for name in required) or features.get("HAVE_VULKAN") != "0":
        raise ValueError("Configured target features differ: " + repr(features))
    record.update({"phase": "configured", "features": features, "generated_config": [{"path": "config.mk", "sha256": sha(config)}, {"path": "config.h", "sha256": sha(work / "source/config.h")}],
                   "sdk_preflight_sha256": sha(work / "sdk-preflight.json"), "vendor_header_probe_sha256": sha(work / "vendor-header-probe.txt"), "compiler_packages_sha256": sha(work / "compiler-packages.tsv")})
    save(work / "build-manifest.json", record)
    return record


def build(work: Path, jobs: int) -> dict:
    lock, record = validate_work(work)
    if not 1 <= jobs <= lock["limits"]["max_jobs"] or record["phase"] not in ("configured", "built"):
        raise ValueError("Configure first and use between one and four jobs")
    for item in record["generated_config"]:
        verify_file(work / "source", item)
    commit = lock["upstream"]["commit"][:9]
    script = "#!/bin/sh\nset -eu\numask 077\ncd /build/source\n"
    script += "make -f Makefile -f /build/sdk-link.mk GIT_VERSION=" + commit + " HAVE_STATIC_VIDEO_FILTERS=1 HAVE_STATIC_AUDIO_FILTERS=1 -j" + str(jobs) + "\n"
    script += "mkdir -p /build/output\ncp retroarch /build/output/retroarch-igm-tg5040\n"
    script += "aarch64-linux-gnu-strip -s /build/output/retroarch-igm-tg5040\n"
    script += "python3 /build/helpers/abi_audit.py /build/output/retroarch-igm-tg5040 /opt/sysroot > /build/sdk-abi-inventory.json\n"
    script += "aarch64-linux-gnu-readelf -h -l -d -V /build/output/retroarch-igm-tg5040 > /build/elf-inventory.txt\n"
    execute_container(work, lock, script, "build-output.log")
    if "/usr/lib/gcc-cross/aarch64-linux-gnu/9/libstdc++.a" not in (work / "build-output.log").read_text().splitlines():
        raise ValueError("Actual full-engine link did not prove GCC9 static C++ runtime selection")
    audit = json.loads((work / "sdk-abi-inventory.json").read_text())
    candidate = work / "output/retroarch-igm-tg5040"
    record.update({"phase": "built", "jobs": jobs, "candidate": {"name": candidate.name, "size": candidate.stat().st_size, "sha256": sha(candidate)},
                   "sdk_dependency_inventory_pass": audit["sdk_dependency_inventory_pass"], "sdk_abi_inventory_sha256": sha(work / "sdk-abi-inventory.json"),
                   "sdk_abi_object_count": len(audit["objects"]), "elf_inventory_sha256": sha(work / "elf-inventory.txt")})
    save(work / "build-manifest.json", record)
    retain(work, record)
    if not audit["sdk_dependency_inventory_pass"]:
        raise ValueError("Full engine linked but SDK library/symbol-version inventory failed; retained as a failed candidate")
    return record


def retain(work: Path, record: dict) -> None:
    """Bundle actual generated configuration and inputs alongside complete sources."""
    names = ("build-manifest.json", LOCK.name, "sdk-link.mk", "sdk-preflight.json", "vendor-header-probe.txt", "sdk-abi-inventory.json", "compiler-packages.tsv", "compiler-version.txt", "elf-inventory.txt", "prepared-sources.json", "source/config.h", "source/config.mk", "container-run.sh")
    with tarfile.open(work / "build-records.tar.gz", "w:gz") as archive:
        for name in names:
            archive.add(work / name, arcname=name)
    record["build_records"] = {"name": "build-records.tar.gz", "size": (work / "build-records.tar.gz").stat().st_size, "sha256": sha(work / "build-records.tar.gz")}
    save(work / "build-manifest.json", record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    first = subparsers.add_parser("prepare")
    first.add_argument("--upstream", type=Path, required=True)
    first.add_argument("--recipe", type=Path, required=True)
    first.add_argument("--work", type=Path, required=True)
    for name in ("configure", "build"):
        step = subparsers.add_parser(name)
        step.add_argument("--work", type=Path, required=True)
        if name == "build":
            step.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.upstream, args.recipe, args.work)
    elif args.command == "configure":
        result = configure(args.work.resolve())
    else:
        result = build(args.work.resolve(), args.jobs)
    print(json.dumps({key: result[key] for key in ("phase", "target_executed", "device_compatibility_proved", "distribution_cleared")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
