#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build an isolated PPSSPP PowerVR candidate; never install an emulator.

Inputs must be complete, pristine pinned source checkouts and verified SDK files.
All source modifications, Docker context, logs, notices and outputs stay in a new
work directory. The source checkout supplied by the caller is read-only here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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


def sdk_search_module():
    spec = importlib.util.spec_from_file_location("ppsspp_sdk_search", Path(__file__).with_name("sdk_search.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def compose_extensions(lock: dict, extension_locks: list[tuple[str, dict]]) -> dict:
    """Compose explicitly selected project patches without changing past evidence.

    Every source preimage still identifies pristine upstream. Postimages are
    applied in the stated extension order, allowing a later patch to extend a
    previously modified translation unit while retaining its exact final hash.
    """
    result = copy.deepcopy(lock)
    preimages = {item["path"]: item["sha256"] for item in result["source_files"]}
    postimages = {item["path"]: item["sha256"] for item in result["patched_files"]}
    patches = list(result["patches"])
    units = []
    extensions = []
    for name, extension in extension_locks:
        if extension.get("upstream_commit") != result["upstream"]["commit"]:
            raise ValueError("Extension upstream commit differs: " + name)
        prerequisites = extension.get("prerequisite_locks", [])
        if not isinstance(prerequisites, list) or any(value not in ["source-lock.json", *extensions] for value in prerequisites):
            raise ValueError("Extension prerequisite lock is missing or out of order: " + name)
        additions = extension.get("patches") or ([extension["patch"]] if "patch" in extension else [])
        if not additions or not extension.get("source_files") or not extension.get("patched_files"):
            raise ValueError("Extension patch/source inventory is incomplete: " + name)
        for item in extension["source_files"]:
            if item["path"] in preimages and preimages[item["path"]] != item["sha256"]:
                raise ValueError("Extension pristine source preimage conflicts: " + item["path"])
            preimages[item["path"]] = item["sha256"]
        postimages.update({item["path"]: item["sha256"] for item in extension["patched_files"]})
        for item in additions:
            if any(old["path"] == item["path"] for old in patches):
                raise ValueError("Extension patch is repeated: " + item["path"])
            patches.append(copy.deepcopy(item))
        units.extend(extension.get("verification_translation_units", []))
        extensions.append(name)
    result["source_files"] = [{"path": name, "sha256": value} for name, value in sorted(preimages.items())]
    result["patched_files"] = [{"path": name, "sha256": value} for name, value in sorted(postimages.items())]
    result["patches"] = patches
    result["enabled_project_extensions"] = extensions
    if extensions:
        result["verification_translation_units"] = sorted(set(units + ["Core/SaveState.cpp"]))
        # The existing source lock belongs to a different completed candidate.
        # Never carry its successful build/hash into this new assembly.
        result["qualification"] = {"full_emulator_build": False, "device_tested": False,
                                   "installed_executable_sha256": None,
                                   "activation": "unqualified extension assembly; separate complete build and device evidence required"}
    return result


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
    if inputs.get("ffmpeg"):
        item = inputs["ffmpeg"]
        if command(["git", "rev-parse", "HEAD"], cwd=source / "ffmpeg") != item["commit"]:
            raise ValueError("FFmpeg submodule commit differs")
        verify_file(source / "ffmpeg" / item["script_path"], item["script_sha256"])
        verify_file(source / "ffmpeg/configure", item["configure_sha256"])
    return modules


def select_rebuilt_ffmpeg(script: str) -> str:
    if script.count("cmake .. ") != 1 or "-DFFMPEG_DIR=" in script:
        raise ValueError("Pinned FFmpeg CMake selection changed")
    return script.replace("cmake .. ", "cmake .. -U 'FFmpeg_INCLUDE_*' -U 'FFmpeg_LIBRARY_*' "
        "-U HAVE_LIBAVCODEC_CONST_AVCODEC -DFFMPEG_DIR=/ffmpeg-sdk ", 1)


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


def prepare(source: Path, recipe: Path, sdk: Path, work: Path, lock: dict, inputs: dict, jobs: int,
            strict_sdk_search: bool = False, rebuild_ffmpeg: bool = False,
            with_state_evidence: bool = False) -> dict:
    if rebuild_ffmpeg and not strict_sdk_search:
        raise ValueError("FFmpeg rebuild requires strict SDK search")
    for root in (source, recipe, sdk, HERE.parents[1]):
        if work == root or root in work.parents:
            raise ValueError("Work directory must be outside all inputs and the project repository")
    extension_locks = []
    recipe_overrides = None
    if with_state_evidence:
        for name in ("state-evidence.lock.json", "state-session.lock.json"):
            path = HERE / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Selected state extension lock is unavailable: " + name)
            extension_locks.append((name, json.loads(path.read_text())))
        lock = compose_extensions(lock, extension_locks)
        overrides_path = HERE / "recipe-overrides.lock.json"
        if overrides_path.is_symlink() or not overrides_path.is_file():
            raise ValueError("Selected state completion recipe overrides are unavailable")
        recipe_overrides = json.loads(overrides_path.read_text())
        if (recipe_overrides.get("upstream_commit") != lock["upstream"]["commit"] or
                recipe_overrides.get("recipe_commit") != inputs["recipe_commit"] or not recipe_overrides.get("patches")):
            raise ValueError("Selected state completion recipe override prerequisites differ")
        for item in recipe_overrides["patches"]:
            verify_file(HERE / item["path"], item["sha256"])
        lock["verification_translation_units"] = sorted(set(lock["verification_translation_units"] + ["SDL/SDLMain.cpp"]))
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
    if strict_sdk_search:
        build_script = sdk_search_module().adapt_script(build_script)
    if rebuild_ffmpeg:
        build_script = select_rebuilt_ffmpeg(build_script)
    (work / "build-candidate.sh").write_text(build_script)
    first = build_script.index("# Apply common patches")
    last = build_script.index("mkdir -p build && cd build", first)
    (work / "rebuild-source.sh").write_text(build_script[:first] +
        "# Corresponding-source archive already contains every applied patch.\n" + build_script[last:])
    for directory in ("output", "ccache"):
        (work / directory).mkdir()
    (work / "upstream-submodules.txt").write_text(modules + "\n")
    if extension_locks:
        shutil.copy2(HERE / "source-lock.json", work / "native-menu-source-lock.json")
        retained_locks = work / "project-extension-locks"
        retained_locks.mkdir()
        for name, _ in extension_locks:
            shutil.copy2(HERE / name, retained_locks / name)
    (work / "source-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    shutil.copy2(HERE / "build-inputs.lock.json", work / "build-inputs.lock.json")
    shutil.copy2(HERE / "build_candidate.py", work / "build_candidate.py")
    for name in ("abi_audit.py", "apply_recipe.py", "sdk_search.py", "ffmpeg_build.py", "build-candidate.md"):
        shutil.copy2(HERE / name, work / name)
    notices = work / "project-notices"
    notices.mkdir()
    for original, name in ((HERE.parent / "LICENSE", "ORIGINAL-PROJECT-MIT.txt"),
                           (HERE / "NOTICE.md", "PPSSPP-PROJECT-NOTICE.md"),
                           (HERE / "LICENSE.PPSSPP.txt", "PPSSPP-GPL-AND-PSPSDK.txt")):
        if original.is_symlink() or not original.is_file():
            raise ValueError("Required project notice is missing: " + str(original))
        shutil.copy2(original, notices / name)
    for item in lock["patches"]:
        destination = work / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / item["path"], destination)
    if recipe_overrides:
        shutil.copy2(HERE / "recipe-overrides.lock.json", work / "recipe-overrides.lock.json")
        for item in recipe_overrides["patches"]:
            destination = work / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HERE / item["path"], destination)
    return {"schema_version": 1, "status": "prepared", "upstream_commit": lock["upstream"]["commit"],
            "recipe_commit": inputs["recipe_commit"], "base_image": inputs["base_image"],
            "project_patch_sha256": lock["patches"][0]["sha256"], "jobs": jobs,
            "project_patches": [{"path": item["path"], "sha256": item["sha256"]} for item in lock["patches"]],
            "enabled_project_extensions": lock.get("enabled_project_extensions", []),
            "extension_locks": [{"name": name, "sha256": digest(HERE / name)} for name, _ in extension_locks],
            "assembled_source_lock_sha256": digest(work / "source-lock.json"),
            "post_recipe_overrides": recipe_overrides["patches"] if recipe_overrides else [],
            "generated_dockerfile_sha256": digest(context / "Dockerfile"),
            "generated_build_script_sha256": digest(work / "build-candidate.sh"),
            "storage_recipe": "one compiler/SDK RUN; read-only SDK mounts; unused SDK/compiler staging removed",
            "strict_sdk_search": strict_sdk_search,
            "rebuild_ffmpeg": rebuild_ffmpeg,
            "executed_builder_sha256": digest(work / "build_candidate.py"),
            "executed_abi_helper_sha256": digest(work / "abi_audit.py"),
            "executed_recipe_runner_sha256": digest(work / "apply_recipe.py"),
            "executed_sdk_search_helper_sha256": digest(work / "sdk_search.py"),
            "executed_ffmpeg_builder_sha256": digest(work / "ffmpeg_build.py"),
            "full_engine_cross_build": False, "device_tested": False,
            "installed_engine_changed": False, "distribution_cleared": False}


def source_bundle(work: Path) -> dict:
    """Retain complete corresponding source, including submodules and notices."""
    source = work / "source"
    bundle = work / "candidate-corresponding-source.tar.gz"
    omitted = {}
    ffmpeg_manifest = work / "ffmpeg-build-inputs/manifest.json"
    if ffmpeg_manifest.is_file() and json.loads(ffmpeg_manifest.read_text()).get("status") == "complete":
        for path in sorted((source / "ffmpeg").rglob("*.a")):
            omitted["ppsspp/" + str(path.relative_to(source))] = {"size": path.stat().st_size, "sha256": digest(path)}
        (work / "omitted-ffmpeg-prebuilt-archives.json").write_text(json.dumps({
            "reason": "unused old prebuilt archives; exact FFmpeg source rebuilt separately; working inputs unchanged",
            "files": omitted}, indent=2) + "\n")
    def retained(item: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(item.name).parts
        if ".git" in parts or parts[:2] == ("ppsspp", "build") or item.name in omitted:
            return None
        item.uid = item.gid = 0
        item.uname = item.gname = ""
        return item
    with tarfile.open(bundle, "w:gz", compresslevel=6, dereference=False) as archive:
        archive.add(source, arcname="ppsspp", filter=retained)
        for name in ("build_candidate.py", "abi_audit.py", "apply_recipe.py", "sdk_search.py", "ffmpeg_build.py", "build-candidate.md",
                     "sdk-search-preflight.json", "local-staged-build.py", "build-candidate.sh", "rebuild-source.sh",
                     "ffmpeg-build-inputs", "omitted-ffmpeg-prebuilt-archives.json",
                     "source-lock.json", "native-menu-source-lock.json", "project-extension-locks", "recipe-overrides.lock.json", "project-notices",
                     "build-inputs.lock.json", "upstream-submodules.txt",
                     "toolchain-packages.txt", "recipe-assembly.json", "recipe-application.log",
                     "combined-tracked-source.patch", "build-configuration", "patches"):
            if (work / name).exists():
                archive.add(work / name, arcname="build/" + name, filter=retained)
        inputs = json.loads((work / "build-inputs.lock.json").read_text())
        for item in inputs["recipe_files"]:
            archive.add(work / "context" / item["path"], arcname="build/recipe/" + item["path"], filter=retained)
        archive.add(work / "context/Dockerfile", arcname="build/recipe/Dockerfile", filter=retained)
        failure = work / "attempts/strict-prebuilt-ffmpeg/failure-evidence.json"
        if failure.is_file():
            archive.add(failure, arcname="build/failed-strict-prebuilt-ffmpeg.json", filter=retained)
    return {"name": bundle.name, "size": bundle.stat().st_size, "sha256": digest(bundle), "gzip_compression_level": 6}


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
    units = ["Core/KeyMap.cpp", "UI/NativeApp.cpp", "UI/GameSettingsScreen.cpp"]
    lock_path = work / "source-lock.json"
    if lock_path.is_file():
        units.extend(json.loads(lock_path.read_text()).get("verification_translation_units", []))
    for unit in dict.fromkeys(units):
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
    configuration = work / "build-configuration"
    configuration.mkdir(exist_ok=True)
    packages = docker(["run", "--rm", "--mount", f"type=bind,src={configuration},dst=/configuration",
        "--entrypoint", "/bin/sh", tag, "-c",
        "cp /tmp/pvr-toolchain.cmake /configuration/pvr-toolchain.cmake && "
        "aarch64-linux-gnu-g++ --version && cmake --version && dpkg-query -W"])
    (work / "toolchain-packages.txt").write_text(packages + "\n")
    report["generated_toolchain_sha256"] = digest(configuration / "pvr-toolchain.cmake")
    if report.get("strict_sdk_search"):
        report["stage"] = "sdk-search-preflight"
        preflight = docker(["run", "--rm",
            "--mount", f"type=bind,src={work / 'sdk_search.py'},dst=/sdk_search.py,readonly",
            "--mount", f"type=bind,src={work / 'abi_audit.py'},dst=/abi_audit.py,readonly",
            "--entrypoint", "python3", tag, "/sdk_search.py"])
        (work / "sdk-search-preflight.json").write_text(preflight + "\n")
        if json.loads(preflight).get("status") != "pass":
            raise ValueError("SDK header/library search preflight failed")
        report["sdk_search_preflight_sha256"] = digest(work / "sdk-search-preflight.json")
    if report.get("rebuild_ffmpeg"):
        if not report.get("strict_sdk_search"):
            raise ValueError("FFmpeg rebuild requires strict SDK search")
        report["stage"] = "ffmpeg-source-build"
        ffmpeg_args = ["run", "--rm"]
        for name, target, readonly in (("source", "/build/ppsspp", True),
                ("ffmpeg-build", "/ffmpeg-build", False), ("ffmpeg-sdk", "/ffmpeg-sdk", False),
                ("ffmpeg-build-inputs", "/ffmpeg-build-inputs", False),
                ("ffmpeg_build.py", "/ffmpeg_build.py", True), ("sdk_search.py", "/sdk_search.py", True),
                ("build-inputs.lock.json", "/build-inputs.lock.json", True)):
            if not readonly:
                (work / name).mkdir(exist_ok=True)
            ffmpeg_args += ["--mount", f"type=bind,src={work / name},dst={target}" + (",readonly" if readonly else "")]
        ffmpeg_args += ["--entrypoint", "/bin/sh", tag, "-c",
            "git config --global --add safe.directory /build/ppsspp/ffmpeg && "
            "exec python3 /ffmpeg_build.py /build/ppsspp/ffmpeg /ffmpeg-build /ffmpeg-sdk "
            "/ffmpeg-build-inputs /build-inputs.lock.json --jobs " + str(report["jobs"])]
        docker(ffmpeg_args, log=work / "ffmpeg-build.log")
        report["ffmpeg_source_build"] = json.loads((work / "ffmpeg-build-inputs/manifest.json").read_text())
        if report["ffmpeg_source_build"].get("status") != "complete":
            raise ValueError("FFmpeg source rebuild was not proved")
    report["stage"] = "recipe-assembly"
    assembly_args = ["run", "--rm"]
    for relative, target in (("source", "/build/ppsspp"), ("context", "/recipe"),
                             ("apply_recipe.py", "/apply_recipe.py"),
                             ("source-lock.json", "/source-lock.json"),
                             ("build-inputs.lock.json", "/build-inputs.lock.json")):
        readonly = "" if relative == "source" else ",readonly"
        assembly_args += ["--mount", f"type=bind,src={work / relative},dst={target}{readonly}"]
    override_arguments = (" --override-lock /provenance/recipe-overrides.lock.json --override-root /provenance"
                          if report.get("post_recipe_overrides") else "")
    assembly_args += ["--mount", f"type=bind,src={work},dst=/provenance",
        "--entrypoint", "/bin/sh", tag, "-c",
        "git config --global --add safe.directory /build/ppsspp && "
        "exec python3 /apply_recipe.py /build/ppsspp /recipe /source-lock.json /build-inputs.lock.json /provenance" + override_arguments]
    assembly_output = docker(assembly_args)
    report["recipe_assembly"] = json.loads(assembly_output)
    if report["recipe_assembly"].get("status") != "applied":
        raise ValueError("Pinned recipe assembly was not proved")
    report["stage"] = "engine"
    arguments = ["run", "--rm"]
    for relative, target in (("source", "/build/ppsspp"), ("output", "/output"),
                             ("ccache", "/ccache"), ("rebuild-source.sh", "/build-candidate.sh")):
        arguments += ["--mount", f"type=bind,src={work / relative},dst={target}"]
    if report.get("rebuild_ffmpeg"):
        arguments += ["--mount", f"type=bind,src={work / 'ffmpeg-sdk'},dst=/ffmpeg-sdk,readonly"]
    arguments += ["--entrypoint", "/bin/sh", tag, "-c",
                  "git config --global --add safe.directory /build/ppsspp && exec /bin/bash /build-candidate.sh"]
    report["git_trust"] = "exact /build/ppsspp allowlist inside ephemeral build containers only"
    report["compiled_build_script_sha256"] = digest(work / "rebuild-source.sh")
    docker(arguments, log=work / "engine-build.log")
    report["build_configuration"] = retain_build_configuration(work)
    if report.get("rebuild_ffmpeg"):
        cache = (work / "source/build/CMakeCache.txt").read_text()
        for component in ("avcodec", "avformat", "avutil", "swresample", "swscale"):
            if not re.search(r"^FFmpeg_LIBRARY_" + component + r":[^=]*=/ffmpeg-sdk/lib/lib" + component + r"\.a$", cache, re.M):
                raise ValueError("FFmpeg library cache did not select rebuilt prefix: " + component)
            if not re.search(r"^FFmpeg_INCLUDE_" + component + r":[^=]*=/ffmpeg-sdk/include$", cache, re.M):
                raise ValueError("FFmpeg header cache did not select rebuilt prefix: " + component)
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
    parser.add_argument("--strict-sdk-search", action="store_true",
                        help="Use proved GCC9/SDK include and library order; require cross-link preflight")
    parser.add_argument("--rebuild-ffmpeg", action="store_true",
                        help="Rebuild pinned FFmpeg out of tree; requires --strict-sdk-search")
    parser.add_argument("--with-state-evidence", action="store_true",
                        help="Compose locked state evidence and session patches; invalidates previous candidate build evidence")
    parser.add_argument("--ca-bundle", type=Path, default=Path("/etc/ssl/certs/ca-certificates.crt"))
    args = parser.parse_args()
    work = args.work_dir.resolve()
    lock = json.loads((HERE / "source-lock.json").read_text())
    inputs = json.loads((HERE / "build-inputs.lock.json").read_text())
    report = prepare(args.source_root.resolve(), args.recipe_root.resolve(), args.sdk_dir.resolve(),
                     work, lock, inputs, args.jobs, args.strict_sdk_search, args.rebuild_ffmpeg,
                     args.with_state_evidence)
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
