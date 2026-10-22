#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build an isolated PPSSPP PowerVR candidate; never install an emulator.

Inputs must be complete, pristine pinned source checkouts and verified SDK files.
All source modifications, Docker context, logs, notices and outputs stay in a new
work directory. The source checkout supplied by the caller is read-only here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
SELECTORS = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(data)
    return hasher.hexdigest()


def command(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, text=True, check=True, capture_output=True).stdout.strip()


def checkout(path: Path, commit: str) -> None:
    if command(["git", "rev-parse", "HEAD"], cwd=path) != commit:
        raise ValueError("Source commit differs: " + str(path))
    if command(["git", "status", "--porcelain", "--ignored", "--untracked-files=all"], cwd=path):
        raise ValueError("Source checkout is not pristine: " + str(path))


def verify_file(path: Path, expected: str, size: int | None = None) -> None:
    if path.is_symlink() or not path.is_file() or digest(path) != expected:
        raise ValueError("Input hash differs: " + str(path))
    if size is not None and path.stat().st_size != size:
        raise ValueError("Input size differs: " + str(path))


def validate(source: Path, recipe: Path, sdk: Path, lock: dict, inputs: dict) -> str:
    checkout(source, lock["upstream"]["commit"])
    checkout(recipe, inputs["recipe_commit"])
    sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"],
                            cwd=source, text=True, capture_output=True)
    if sparse.stdout.strip() == "true":
        raise ValueError("A full upstream checkout is required, not sparse source")
    modules = command(["git", "submodule", "status", "--recursive"], cwd=source)
    if not modules or any(line[:1] in ("-", "+", "U") for line in modules.splitlines()):
        raise ValueError("Submodules are missing or differ from pinned gitlinks")
    if command(["git", "submodule", "foreach", "--quiet", "--recursive",
                "git status --porcelain --ignored --untracked-files=all"], cwd=source):
        raise ValueError("Submodule working trees are not pristine")
    for item in lock["source_files"]:
        verify_file(source / item["path"], item["sha256"])
    for item in lock["patches"]:
        verify_file(HERE / item["path"], item["sha256"])
    for item in inputs["recipe_files"]:
        verify_file(recipe / item["path"], item["sha256"])
    for item in inputs["sdk_assets"]:
        verify_file(sdk / item["name"], item["sha256"], item["size"])
    return modules


def docker(args: list[str], *, log: Path | None = None) -> str:
    environment = os.environ.copy()
    for name in SELECTORS:
        environment.pop(name, None)
    argv = ["docker", "--host=unix:///var/run/docker.sock"] + args
    if log:
        with log.open("w") as stream:
            subprocess.run(argv, env=environment, stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
        return ""
    return subprocess.run(argv, env=environment, text=True,
                          capture_output=True, check=True).stdout.strip()


def render_dockerfile(original: str, inputs: dict) -> str:
    """Keep compiler/sysroot commands, without cumulative SDK image layers."""
    if original.count("FROM ubuntu:20.04") != 1:
        raise ValueError("Recipe base-image instruction changed")
    apt_start = original.index("RUN apt-get update") + len("RUN ")
    apt_end = original.index("# Extract Linaro", apt_start)
    apt = "apt-get -o Acquire::Retries=3 -o Acquire::https::CaInfo=/run/secrets/proxy_ca"
    install = original[apt_start:apt_end].strip().replace("apt-get", apt)
    toolchain_start = original.index("RUN printf") + len("RUN ")
    toolchain_end = original.index("COPY build-pvr.sh", toolchain_start)
    toolchain = original[toolchain_start:toolchain_end].strip()
    mounts = ["--mount=type=secret,id=proxy_ca,required=true"]
    mounts += [f"--mount=type=bind,source={item['name']},target=/run/{item['name']},readonly"
               for item in inputs["sdk_assets"]]
    mounts += ["--mount=type=bind,source=build-pvr.sh,target=/run/build-pvr.sh,readonly",
               "--mount=type=bind,source=patches,target=/run/recipe-patches,readonly"]
    commands = [install,
        "tar xzf /run/aarch64-linux-gnu-7.5.0-linaro.tgz -C /opt/",
        "mkdir -p /opt/smartpro-sdk",
        "tar xzf /run/SDK_usr_tg5040_a133p.tgz -C /opt/smartpro-sdk/",
        "cp -a /opt/aarch64-linux-gnu-7.5.0-linaro/aarch64-linux-gnu/libc /opt/sysroot",
        "cp -a /opt/smartpro-sdk/usr/include/* /opt/sysroot/usr/include/",
        "cp -a /opt/smartpro-sdk/usr/lib/* /opt/sysroot/usr/lib/", toolchain,
        "cp /run/build-pvr.sh /build-pvr.sh",
        "chmod +x /build-pvr.sh", "cp -a /run/recipe-patches /patches",
        "mkdir -p /build",
        "rm -rf /opt/aarch64-linux-gnu-7.5.0-linaro /opt/smartpro-sdk"]
    return ("# syntax=docker/dockerfile:1\nFROM " + inputs["base_image"] +
            "\nENV DEBIAN_FRONTEND=noninteractive\nRUN " + " \\\n    ".join(mounts) +
            " \\\n    " + " && \\\n    ".join(commands) +
            '\nWORKDIR /build\nENTRYPOINT ["/build-pvr.sh"]\n')


def prepare(source: Path, recipe: Path, sdk: Path, work: Path, lock: dict, inputs: dict, jobs: int) -> dict:
    for root in (source, recipe, sdk, HERE.parents[1]):
        if work == root or root in work.parents:
            raise ValueError("Work directory must be outside all inputs and the project repository")
    modules = validate(source, recipe, sdk, lock, inputs)
    if work.exists():
        raise ValueError("Work directory must be new: " + str(work))
    work.mkdir(parents=True)
    candidate = work / "source"
    shutil.copytree(source, candidate, symlinks=True)
    for item in lock["patches"]:
        command(["git", "apply", "--check", str(HERE / item["path"])], cwd=candidate)
        command(["git", "apply", str(HERE / item["path"])], cwd=candidate)
    for item in lock["patched_files"]:
        verify_file(candidate / item["path"], item["sha256"])
    context = work / "context"
    context.mkdir()
    for item in inputs["sdk_assets"]:
        shutil.copy2(sdk / item["name"], context / item["name"])
    for item in inputs["recipe_files"]:
        destination = context / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(recipe / item["path"], destination)
    (context / "Dockerfile").write_text(render_dockerfile((context / "Dockerfile.pvr").read_text(), inputs))
    build_script = (recipe / "build-pvr.sh").read_text()
    if build_script.count("make -j$(nproc) PPSSPPSDL") != 1:
        raise ValueError("Recipe build target/concurrency changed")
    build_script = build_script.replace("make -j$(nproc) PPSSPPSDL", f"make -j{jobs} PPSSPPSDL")
    (work / "build-candidate.sh").write_text(build_script)
    first = build_script.index("# Apply common patches")
    last = build_script.index("mkdir -p build && cd build", first)
    (work / "rebuild-source.sh").write_text(build_script[:first] +
        "# Corresponding-source archive already contains every applied patch.\n" + build_script[last:])
    for directory in ("output", "ccache"):
        (work / directory).mkdir()
    (work / "upstream-submodules.txt").write_text(modules + "\n")
    shutil.copy2(HERE / "source-lock.json", work / "source-lock.json")
    shutil.copy2(HERE / "build-inputs.lock.json", work / "build-inputs.lock.json")
    shutil.copy2(HERE / "build_candidate.py", work / "build_candidate.py")
    for name in ("abi_audit.py", "apply_recipe.py"):
        shutil.copy2(HERE / name, work / name)
    for item in lock["patches"]:
        destination = work / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / item["path"], destination)
    return {"schema_version": 1, "status": "prepared", "upstream_commit": lock["upstream"]["commit"],
            "recipe_commit": inputs["recipe_commit"], "base_image": inputs["base_image"],
            "project_patch_sha256": lock["patches"][0]["sha256"], "jobs": jobs,
            "generated_dockerfile_sha256": digest(context / "Dockerfile"),
            "generated_build_script_sha256": digest(work / "build-candidate.sh"),
            "storage_recipe": "one compiler/SDK RUN; read-only SDK mounts; unused SDK/compiler staging removed",
            "full_engine_cross_build": False, "device_tested": False,
            "installed_engine_changed": False, "distribution_cleared": False}


def source_bundle(work: Path) -> dict:
    """Retain complete corresponding source, including submodules and notices."""
    source = work / "source"
    bundle = work / "candidate-corresponding-source.tar.gz"
    def retained(item: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(item.name).parts
        if ".git" in parts or parts[:2] == ("ppsspp", "build"):
            return None
        item.uid = item.gid = 0
        item.uname = item.gname = ""
        return item
    with tarfile.open(bundle, "w:gz", dereference=False) as archive:
        archive.add(source, arcname="ppsspp", filter=retained)
        for name in ("build_candidate.py", "abi_audit.py", "apply_recipe.py", "build-candidate.sh", "rebuild-source.sh",
                     "source-lock.json", "build-inputs.lock.json", "upstream-submodules.txt",
                     "toolchain-packages.txt", "recipe-assembly.json", "recipe-application.log",
                     "combined-tracked-source.patch", "build-configuration", "patches"):
            if (work / name).exists():
                archive.add(work / name, arcname="build/" + name, filter=retained)
        inputs = json.loads((work / "build-inputs.lock.json").read_text())
        for item in inputs["recipe_files"]:
            archive.add(work / "context" / item["path"], arcname="build/recipe/" + item["path"], filter=retained)
        archive.add(work / "context/Dockerfile", arcname="build/recipe/Dockerfile", filter=retained)
    return {"name": bundle.name, "size": bundle.stat().st_size, "sha256": digest(bundle)}


def retain_build_configuration(work: Path) -> dict:
    build_root = work / "source/build"
    destination = work / "build-configuration"
    destination.mkdir(exist_ok=True)
    for name in ("git-version.cpp", "CMakeCache.txt", "ppsspp_config.h"):
        if (build_root / name).is_file():
            shutil.copy2(build_root / name, destination / name)
    if not (destination / "git-version.cpp").is_file():
        raise ValueError("Generated PPSSPP version source is missing")
    result = {}
    for unit in ("Core/KeyMap.cpp", "UI/NativeApp.cpp", "UI/GameSettingsScreen.cpp"):
        matches = []
        for makefile in build_root.rglob("build.make"):
            if unit + ".o" in makefile.read_text():
                flags = makefile.parent / "flags.make"
                if flags.is_file():
                    matches.append(flags)
        if len(matches) != 1:
            raise ValueError("Ambiguous or missing translation-unit flags: " + unit)
        flags = matches[0]
        content = flags.read_text()
        if not re.search(r"(?:^|\s)-DSDL(?:=\S+)?(?:\s|$)", content):
            raise ValueError("SDL definition is absent from translation unit: " + unit)
        relative = flags.relative_to(build_root)
        copied = destination / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(flags, copied)
        result[unit] = {"sdl_defined": True, "flags_path": str(relative), "flags_sha256": digest(flags),
                        "definitions": re.findall(r"^CXX_DEFINES = (.*)$", content, re.M),
                        "compile_flags": re.findall(r"^CXX_FLAGS = (.*)$", content, re.M)}
    return {"translation_units": result, "git_version_cpp_sha256": digest(destination / "git-version.cpp"),
            "cmake_cache_sha256": digest(destination / "CMakeCache.txt") if (destination / "CMakeCache.txt").is_file() else None}


def build(work: Path, report: dict, ca: Path) -> None:
    docker(["info", "--format", "{{.ServerVersion}}"])
    tag = "trimui-ppsspp-pvr:" + report["project_patch_sha256"][:12]
    report["stage"] = "image"
    docker(["build", "--secret", "id=proxy_ca,src=" + str(ca), "--tag", tag,
            str(work / "context")], log=work / "image-build.log")
    report["image_id"] = docker(["image", "inspect", "--format", "{{.Id}}", tag])
    packages = docker(["run", "--rm", "--entrypoint", "/bin/sh", tag, "-c",
        "aarch64-linux-gnu-g++ --version; cmake --version; dpkg-query -W"])
    (work / "toolchain-packages.txt").write_text(packages + "\n")
    report["stage"] = "recipe-assembly"
    assembly_args = ["run", "--rm"]
    for relative, target in (("source", "/build/ppsspp"), ("context", "/recipe"),
                             ("apply_recipe.py", "/apply_recipe.py"),
                             ("source-lock.json", "/source-lock.json"),
                             ("build-inputs.lock.json", "/build-inputs.lock.json")):
        readonly = "" if relative == "source" else ",readonly"
        assembly_args += ["--mount", f"type=bind,src={work / relative},dst={target}{readonly}"]
    assembly_args += ["--mount", f"type=bind,src={work},dst=/provenance",
        "--entrypoint", "/bin/sh", tag, "-c",
        "git config --global --add safe.directory /build/ppsspp && "
        "exec python3 /apply_recipe.py /build/ppsspp /recipe /source-lock.json /build-inputs.lock.json /provenance"]
    assembly_output = docker(assembly_args)
    report["recipe_assembly"] = json.loads(assembly_output)
    if report["recipe_assembly"].get("status") != "applied":
        raise ValueError("Pinned recipe assembly was not proved")
    report["stage"] = "engine"
    arguments = ["run", "--rm"]
    for relative, target in (("source", "/build/ppsspp"), ("output", "/output"),
                             ("ccache", "/ccache"), ("rebuild-source.sh", "/build-candidate.sh")):
        arguments += ["--mount", f"type=bind,src={work / relative},dst={target}"]
    arguments += ["--entrypoint", "/bin/sh", tag, "-c",
                  "git config --global --add safe.directory /build/ppsspp && exec /bin/bash /build-candidate.sh"]
    report["git_trust"] = "exact /build/ppsspp allowlist inside ephemeral build containers only"
    report["compiled_build_script_sha256"] = digest(work / "rebuild-source.sh")
    docker(arguments, log=work / "engine-build.log")
    report["build_configuration"] = retain_build_configuration(work)
    binary = work / "output/PPSSPPSDL_TrimUI"
    verify = docker(["run", "--rm", "--mount", f"type=bind,src={work / 'output'},dst=/candidate,readonly",
        "--entrypoint", "/bin/sh", tag, "-c",
        "aarch64-linux-gnu-readelf -h -d -V /candidate/PPSSPPSDL_TrimUI"])
    (work / "candidate-elf.txt").write_text(verify + "\n")
    if not re.search(r"Machine:\s+AArch64", verify):
        raise ValueError("Candidate is not an AArch64 ELF")
    report["binary"] = {"name": binary.name, "size": binary.stat().st_size, "sha256": digest(binary),
                         "needed": re.findall(r"Shared library: \[([^]]+)\]", verify)}
    report["full_engine_cross_build"] = True
    audit = docker(["run", "--rm", "--mount", f"type=bind,src={work / 'output'},dst=/candidate,readonly",
        "--mount", f"type=bind,src={work / 'abi_audit.py'},dst=/abi_audit.py,readonly",
        "--entrypoint", "python3", tag, "/abi_audit.py", "/candidate/PPSSPPSDL_TrimUI", "/opt/sysroot"])
    (work / "candidate-abi.json").write_text(audit + "\n")
    report["sdk_dependency_inventory_pass"] = json.loads(audit)["sdk_dependency_inventory_pass"]
    report["stage"] = "source-retention"
    report["corresponding_source"] = source_bundle(work)
    report["status"] = "cross-built-unqualified"
    report["stage"] = "complete"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--recipe-root", type=Path, required=True)
    parser.add_argument("--sdk-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4, choices=range(1, 33))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--ca-bundle", type=Path, default=Path("/etc/ssl/certs/ca-certificates.crt"))
    args = parser.parse_args()
    work = args.work_dir.resolve()
    lock = json.loads((HERE / "source-lock.json").read_text())
    inputs = json.loads((HERE / "build-inputs.lock.json").read_text())
    report = prepare(args.source_root.resolve(), args.recipe_root.resolve(), args.sdk_dir.resolve(),
                     work, lock, inputs, args.jobs)
    try:
        if not args.prepare_only:
            build(work, report, args.ca_bundle.resolve())
    except (subprocess.CalledProcessError, ValueError) as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        (work / "candidate-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
