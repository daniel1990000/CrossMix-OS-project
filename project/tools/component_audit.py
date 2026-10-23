#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check recorded native component/custody scope without granting rights.

Reads a fixed set of repository records and optional source references. It does
not download archives, run builds, inspect private storage or change selection.
An internally consistent report is not a legal or distribution decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import unquote, urlsplit

from tools.recovery_preflight import directory_fd, fingerprint

MAX_INPUT = 4 * 1024 ** 2
MAX_ROWS = 256
ROOT = Path(__file__).absolute().parents[2]
INPUTS = {
    "ledger": "project/docs/native-component-ledger.json",
    "release": "project/packaging/current-release.json",
    "rebuild": "project/evidence/artifact-custody/native-rebuild.json",
    "retention": "project/evidence/artifact-custody/native-retention.json",
    "ppsspp_lock": "project/ppsspp/source-lock.json",
    "retroarch_lock": "project/retroarch/source-lock.json",
}
SCOPES = {
    "original-build-helpers": ("build-tools", "both"),
    "ppsspp-engine-and-project-patches": ("compiled-engine", "ppsspp"),
    "ppsspp-spruce-recipe": ("build-recipe-and-inserted-code", "ppsspp"),
    "ffmpeg-five-static-libraries": ("static-library", "ppsspp"),
    "ffmpeg-jpeg-code": ("compiled-code-notices", "ppsspp"),
    "gcc9-static-cxx-runtime-and-headers": ("incorporated-runtime-and-headers", "both"),
    "ppsspp-glslang-and-spirv-cross": ("static-library", "ppsspp"),
    "ppsspp-zstd-and-libchdr": ("static-library", "ppsspp"),
    "ppsspp-inline-licence-components": ("inline-source-notices", "ppsspp"),
    "ppsspp-other-embedded-components": ("compiled-component-backlog", "ppsspp"),
    "retroarch-engine-and-project-patch": ("compiled-engine", "retroarch"),
    "retroarch-spruce-igm-and-recipe": ("build-recipe-and-inserted-code", "retroarch"),
    "retroarch-static-filters-and-thirdparty": ("static-library", "retroarch"),
    "vendor-sdk-and-linaro-sysroot": ("sdk-headers-startup-and-libraries", "both"),
    "device-dynamic-libraries": ("target-dynamic-dependency", "both"),
    "native-assets-and-adjacent-data": ("runtime-assets", "both"),
}
CANDIDATES = {
    "ppsspp-complete-state-candidate": ("ppsspp", "historical"),
    "retroarch-igm-candidate": ("retroarch", "historical"),
    "ppsspp-state-r04-rebuild": ("ppsspp", "r04-replacement"),
    "retroarch-igm-r04-rebuild": ("retroarch", "r04-replacement"),
}
RETENTION_ROLES = {
    "ppsspp-binary": "ppsspp-binary",
    "ppsspp-corresponding-source": "ppsspp-source",
    "ppsspp-build-records": "ppsspp-build-records",
    "retroarch-binary": "ra-binary",
    "retroarch-corresponding-source": "ra-source",
    "retroarch-build-records": "ra-build-records",
    "compiler-image-private-sdk-containing": "compiler-image",
}
PROJECT_PATCH_FILES = {
    "ppsspp": ("patches/0001-independent-native-menu-controls.patch",
               "patches/0002-save-slot-completion-evidence.patch",
               "patches/0003-project-state-session.patch",
               "patches/0004-checked-spruce-save-and-quit.patch"),
    "retroarch": ("patches/0001-independent-igm-menu-controls.patch",),
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")


class AuditError(ValueError):
    """A bounded record is missing, malformed or inconsistent."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def relative(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096 and
            value == str(PurePosixPath(value)) and not value.startswith("/") and
            ".." not in PurePosixPath(value).parts and "\\" not in value and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), "invalid relative record path")
    return value


def safe_bytes(root, name):
    """Read one bounded regular file through no-follow directory descriptors."""
    parts = PurePosixPath(relative(name)).parts
    fd = directory_fd(root)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                       dir_fd=fd)
        try:
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_INPUT,
                    "record must be a bounded nonempty regular file")
            chunks, count = [], 0
            while count <= MAX_INPUT:
                block = os.read(leaf, min(65536, MAX_INPUT + 1 - count))
                if not block:
                    break
                chunks.append(block)
                count += len(block)
            require(count == before.st_size and fingerprint(before) == fingerprint(os.fstat(leaf)),
                    "record changed during inspection")
            return b"".join(chunks)
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_documents(root=ROOT):
    documents, provenance = {}, {}
    for key, name in INPUTS.items():
        raw = safe_bytes(root, name)
        try:
            value = json.loads(raw, object_pairs_hook=unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(AuditError("nonfinite JSON")))
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise AuditError("invalid JSON repository record") from exc
        require(isinstance(value, dict), "record must be a JSON object")
        documents[key] = value
        provenance[key] = {"path": name, "size_bytes": len(raw),
                           "sha256": hashlib.sha256(raw).hexdigest()}
    return documents, provenance


def rows(value, field, identifier):
    require(isinstance(value, list) and 0 < len(value) <= MAX_ROWS, "invalid " + field + " rows")
    result = {}
    for item in value:
        require(isinstance(item, dict), "invalid " + field + " row")
        key = item.get(identifier)
        require(isinstance(key, str) and 0 < len(key) <= 256 and key not in result,
                "invalid or duplicate " + field + " identifier")
        result[key] = item
    return result


def sha(value):
    require(isinstance(value, str) and SHA256.fullmatch(value), "invalid SHA-256 identity")
    return value


def commit(value):
    require(isinstance(value, str) and SHA1.fullmatch(value), "exact source commit required")
    return value


def artifact(record, size_key="size"):
    require(isinstance(record, dict), "artifact record required")
    sha(record.get("sha256"))
    require(type(record.get(size_key)) is int and 0 < record[size_key] <= 2 ** 40,
            "invalid artifact size")
    return record["sha256"], record[size_key]


def validate_identities(value, depth=0):
    """Validate structured identity fields, leaving prose observations as prose."""
    require(depth <= 32, "component identity nesting exceeds budget")
    if isinstance(value, dict):
        require(len(value) <= MAX_ROWS, "component identity map exceeds budget")
        for key, item in value.items():
            require(isinstance(key, str), "component identity keys must be strings")
            if key == "sha256" or key.endswith("_sha256"):
                sha(item)
            elif key == "commit" or key.endswith("_commit") or key.endswith("_gitlink"):
                commit(item)
            else:
                validate_identities(item, depth + 1)
    elif isinstance(value, list):
        require(len(value) <= MAX_ROWS, "component identity list exceeds budget")
        for item in value:
            validate_identities(item, depth + 1)


def recorded_custody(rebuild, retention):
    """Cross-check prior receipts only; never claim fresh remote retrieval."""
    source = rows(rebuild.get("artifacts"), "rebuild artifact", "role")
    retained = rows(retention.get("artifacts"), "retained artifact", "id")
    require(set(source) == set(RETENTION_ROLES) and set(retained) == set(RETENTION_ROLES.values()),
            "native custody artifact scope differs")
    checked = {}
    for role, retained_id in RETENTION_ROLES.items():
        expected = artifact(source[role])
        receipt = retained[retained_id]
        require(artifact(receipt, "size_bytes") == expected and
                receipt.get("full_reassembly_sha256") == expected[0] and
                receipt.get("full_reassembly_size_bytes") == expected[1],
                "rebuild and retained artifact identities differ")
        parts = receipt.get("parts")
        require(isinstance(parts, list) and 0 < len(parts) <= 64, "invalid retained part count")
        count = 0
        for order, part in enumerate(parts):
            require(isinstance(part, dict) and type(part.get("order")) is int and
                    part["order"] == order, "retained part order differs")
            _, size = artifact(part, "size_bytes")
            require(size <= 64 * 1024 ** 2, "retained part exceeds recorded limit")
            count += size
        require(count == expected[1], "retained part sizes do not match full artifact")
        retrieval = (receipt.get("retained_storage_retrieval_verified") is True and
                     all(p.get("retrieval_verified") is True for p in parts))
        checked[role] = {"sha256": expected[0], "size_bytes": expected[1],
                         "prior_receipt_reports_retrieval": retrieval}
    return checked


def source_checks(ledger, reference_roots):
    """Check fixed recorded file bytes, not arbitrary paths or Git execution."""
    evidence = ledger.get("fresh_primary_source_review", {}).get("source_files")
    source_rows = rows(evidence, "primary source", "id")
    result = []
    for key in sorted(source_rows):
        row = source_rows[key]
        sha(row.get("sha256_of_returned_text"))
        commit(row.get("git_blob_sha"))
        url = row.get("immutable_url", row.get("url"))
        require(isinstance(url, str), "source URL required")
        parsed = urlsplit(url)
        parts = unquote(parsed.path).strip("/").split("/")
        require(parsed.scheme == "https" and parsed.netloc == "github.com" and
                len(parts) >= 5 and parts[2] == "blob", "invalid pinned source URL")
        repository, revision = "/".join(parts[:2]), parts[3]
        commit(revision)
        path = relative("/".join(parts[4:]))
        scope = row.get("scope")
        require(scope == "whole file" or isinstance(scope, str) and re.fullmatch(r"lines [1-9][0-9]*-[1-9][0-9]*", scope),
                "unknown source excerpt scope")
        report = {"id": key, "repository": repository, "commit": revision,
                  "path": path, "scope": scope, "status": "reference-not-supplied"}
        if repository in reference_roots:
            try:
                raw = safe_bytes(reference_roots[repository], path)
            except FileNotFoundError:
                report["status"] = "file-not-in-sparse-reference"
            else:
                blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                require(blob == row["git_blob_sha"], "reference file Git blob identity differs")
                if scope == "whole file":
                    require(hashlib.sha256(raw).hexdigest() == row["sha256_of_returned_text"],
                            "whole-file source digest differs")
                # Excerpt text may have provider newline normalization. The full
                # blob identifies it; never compare an excerpt digest to a file.
                report["status"] = "whole-file-identity-matched"
        result.append(report)
    return result


def project_patch_checks(documents, components, project_root):
    """Join repeated records to known project files, never ledger-supplied paths."""
    actual, checks = {}, []
    for engine, paths in PROJECT_PATCH_FILES.items():
        actual[engine] = {}
        for path in paths:
            fixed_path = "project/" + engine + "/" + path
            digest = hashlib.sha256(safe_bytes(project_root, fixed_path)).hexdigest()
            actual[engine][path] = digest
            checks.append({"path": fixed_path, "sha256": digest})

    def exact(records, expected, label):
        entries = rows(records, label, "path")
        require(set(entries) == set(expected), "project patch scope differs")
        for path, digest in expected.items():
            require(entries[path].get("sha256") == digest, "project patch digest differs from fixed file")

    pp = components["ppsspp-engine-and-project-patches"]["identity"]
    exact(pp.get("project_patches", []) + pp.get("post_recipe_overrides", []),
          actual["ppsspp"], "component PPSSPP patch")
    rebuilt = documents["rebuild"]["ppsspp"]
    exact(rebuilt.get("project_patches", []) + rebuilt.get("post_recipe_overrides", []),
          actual["ppsspp"], "R04 PPSSPP patch")
    pp_locked = documents["ppsspp_lock"].get("patches")
    require(isinstance(pp_locked, list), "PPSSPP patch lock required")
    pp_locked_rows = rows(pp_locked, "PPSSPP source-lock patch", "path")
    require(set(pp_locked_rows) == {PROJECT_PATCH_FILES["ppsspp"][0]}, "unexpected primary PPSSPP patch lock scope")
    exact(pp_locked, {path: actual["ppsspp"][path] for path in pp_locked_rows}, "PPSSPP source-lock patch")
    ra = components["retroarch-engine-and-project-patch"]["identity"]
    exact([ra.get("project_patch")], actual["retroarch"], "component RetroArch patch")
    exact([documents["retroarch_lock"].get("patch")], actual["retroarch"], "RetroArch source-lock patch")
    return checks


def audit(documents, *, candidates=None, reference_roots=None, project_root=ROOT):
    require(isinstance(documents, dict) and set(documents) == set(INPUTS), "fixed record set required")
    ledger, release = documents["ledger"], documents["release"]
    rebuild, retention = documents["rebuild"], documents["retention"]
    for record in (ledger, release, rebuild, retention):
        require(record.get("schema") == 1 and type(record.get("schema")) is int, "unsupported record schema")
    for key in ("native_binary_distribution_cleared", "source_use_verified", "hardware_qualified",
                "runtime_gates_enabled", "author_contact_sent"):
        require(ledger.get(key) is False, "component review scope cannot be promoted by a record")
    components = rows(ledger.get("components"), "component", "id")
    require(set(components) == set(SCOPES), "component classification scope differs; review the new scope")
    for component in components.values():
        require(component.get("binary_distribution_cleared") is False and
                component.get("review_status") == "open", "component clearance requires separate human review")
        require(isinstance(component.get("identity"), dict) and component["identity"] and
                isinstance(component.get("terms_observed"), str) and component["terms_observed"],
                "component source/terms record required")
        validate_identities(component["identity"])
        require(isinstance(component.get("remaining_evidence"), list) and
                0 < len(component["remaining_evidence"]) <= 32 and
                all(isinstance(x, str) and 0 < len(x) <= 4096 for x in component["remaining_evidence"]),
                "component unresolved evidence scope required")
        require(isinstance(component.get("evidence"), list) and
                0 < len(component["evidence"]) <= 64 and
                all(isinstance(x, str) and 0 < len(x) <= 4096 for x in component["evidence"]),
                "component source evidence references required")
    pp_lock, ra_lock = documents["ppsspp_lock"], documents["retroarch_lock"]
    pins = {
        "ppsspp-engine-and-project-patches": pp_lock["upstream"]["commit"],
        "ppsspp-spruce-recipe": pp_lock["spruce_build_recipe"]["commit"],
        "retroarch-engine-and-project-patch": ra_lock["recipe"]["upstream_commit"],
        "retroarch-spruce-igm-and-recipe": ra_lock["recipe"]["commit"],
        "ffmpeg-five-static-libraries": rebuild["ppsspp"]["ffmpeg_commit"],
        "ffmpeg-jpeg-code": rebuild["ppsspp"]["ffmpeg_commit"],
    }
    for component_id, expected in pins.items():
        require(components[component_id]["identity"].get("commit") == commit(expected),
                "component identity differs from engine/recipe/build pin")
    patch_checks = project_patch_checks(documents, components, project_root)
    references = rows(release.get("optional_native_references"), "native candidate", "id")
    require(set(references) == set(CANDIDATES), "unknown native candidate scope")
    selection = release.get("selected_native_binaries")
    require(isinstance(selection, list) and len(selection) <= len(CANDIDATES) and
            all(isinstance(x, str) and x in references for x in selection) and
            len(set(selection)) == len(selection), "invalid selected native candidate scope")
    for key, row in references.items():
        require(row.get("selected") is (key in selection), "candidate selection disagrees with descriptor")
        sha(row.get("sha256"))
        commit(row.get("source_commit"))
        commit(row.get("recipe_commit"))
        engine, generation = CANDIDATES[key]
        expected_source = pp_lock["upstream"]["commit"] if engine == "ppsspp" else ra_lock["recipe"]["upstream_commit"]
        expected_recipe = pp_lock["spruce_build_recipe"]["commit"] if engine == "ppsspp" else ra_lock["recipe"]["commit"]
        require(row["source_commit"] == expected_source and row["recipe_commit"] == expected_recipe,
                "candidate source/recipe pin differs")
        require(row.get("extension_set") == [engine + "/" + path for path in PROJECT_PATCH_FILES[engine]],
                "candidate project extension scope differs")
        expected_binary = (ledger["historical_candidates"][engine] if generation == "historical" else
                           rebuild[engine]["binary" if engine == "ppsspp" else "candidate"])
        require(row["sha256"] == expected_binary["sha256"], "candidate binary identity differs")
    custody = recorded_custody(rebuild, retention)
    requested = tuple(candidates) if candidates is not None else tuple(
        key for key, (_, generation) in CANDIDATES.items() if generation == "r04-replacement")
    require(0 < len(requested) <= len(CANDIDATES) and len(set(requested)) == len(requested) and
            all(x in CANDIDATES for x in requested), "unknown or duplicate review candidate")
    reports = []
    for key in requested:
        engine, generation = CANDIDATES[key]
        row = references[key]
        if engine == "ppsspp":
            lock = documents["ppsspp_lock"]
            source_pin = lock["upstream"]["commit"]
            recipe_pin = lock["spruce_build_recipe"]["commit"]
        else:
            lock = documents["retroarch_lock"]
            source_pin = lock["recipe"]["upstream_commit"]
            recipe_pin = lock["recipe"]["commit"]
        require(row["source_commit"] == commit(source_pin) and row["recipe_commit"] == commit(recipe_pin),
                "native candidate source/recipe pin differs")
        if generation == "historical":
            require(row["sha256"] == ledger["historical_candidates"][engine]["sha256"],
                    "historical candidate identity changed")
            paired = False
        else:
            binary = rebuild[engine]["binary" if engine == "ppsspp" else "candidate"]
            require(row["sha256"] == binary["sha256"] == custody[engine + "-binary"]["sha256"] and
                    row["source_commit"] == rebuild[engine]["upstream_commit"] and
                    row["recipe_commit"] == rebuild[engine]["recipe_commit"],
                    "replacement candidate differs from paired R04 identity")
            require(artifact(binary) == (custody[engine + "-binary"]["sha256"],
                                         custody[engine + "-binary"]["size_bytes"]),
                    "replacement binary size differs from its artifact record")
            paired = all(custody[engine + suffix]["prior_receipt_reports_retrieval"]
                         for suffix in ("-binary", "-corresponding-source", "-build-records"))
        scope = [{"id": component_id, "classification": classification,
                  "open_evidence_items": len(components[component_id]["remaining_evidence"])}
                 for component_id, (classification, belongs) in SCOPES.items()
                 if belongs in ("both", engine)]
        reports.append({"id": key, "generation": generation, "sha256": row["sha256"],
                        "source_commit": row["source_commit"], "recipe_commit": row["recipe_commit"],
                        "selected": key in selection, "matching_prior_custody_records": paired,
                        "component_scope": scope, "distribution_cleared": False,
                        "status": "blocked-on-component-review"})
    return {"schema": 1, "kind": "native-component-record-consistency", "records_consistent": True,
            "native_distribution_requested": bool(selection), "reviewed_candidates": reports,
            "component_classifications": dict(sorted((k, v[0]) for k, v in SCOPES.items())),
            "project_patch_checks": patch_checks,
            "source_checks": source_checks(ledger, reference_roots or {}),
            "native_binary_distribution_cleared": False, "source_use_verified": False,
            "hardware_qualified": False, "runtime_gates_enabled": False,
            "fresh_remote_retrieval_performed": False,
            "limits": ["Consistency of prior receipts does not freshly retrieve or authenticate their claims.",
                       "Source bytes and licence observations do not settle combined-distribution permission.",
                       "Exact recipe/IGM/SDK grants, component membership and notice/source review remain open."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=tuple(CANDIDATES), action="append")
    parser.add_argument("--ppsspp-source-root", type=Path)
    parser.add_argument("--ra-recipe-root", type=Path)
    parser.add_argument("--require-native-ready", action="store_true",
                        help="exit 3 while external/native distribution review remains open")
    args = parser.parse_args(argv)
    try:
        documents, provenance = read_documents()
        refs = {name: root for name, root in (("hrydgard/ppsspp", args.ppsspp_source_root),
                                             ("spruceUI/RA", args.ra_recipe_root)) if root is not None}
        report = audit(documents, candidates=args.candidate, reference_roots=refs)
        report["input_records"] = provenance
        print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
        return 3 if args.require_native_ready else 0
    except (AuditError, OSError, KeyError, TypeError, ValueError):
        # Never echo untrusted JSON, private workspace paths or OS error text.
        print("component audit failed: malformed, changed or unavailable fixed records", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
