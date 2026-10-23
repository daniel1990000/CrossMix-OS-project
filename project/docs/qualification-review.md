# Device casebook and independent review proposals

`tools/qualification_review.py` checks the existing TG5040 operator recorder's
session, snapshots and append-only attempt chains. It adds structured notes and
context counts to that casebook. It does not create a second attempt database,
start a device case, write a profile, install a candidate or grant qualification.
Its output is a proposal for a human reviewer. D05/D06, N01/N02 and P04 still
require their actual original-device work and the corresponding independent
decisions.

## Prepare exact scope before collecting results

Use the [recorder runbook](device-test-runbook.md) and the independently reviewed
candidate. Complete actual recovery, inventory and source-use prerequisites
before device execution. Keep the session and raw evidence in private storage
outside the inspected card, and retrieve retained copies before relying on them.

Create the recorder session using an independently prepared expected profile.
For a candidate review, that profile's `baseline_files` must include the complete
reviewed installed source and original payload, including transitive imports and
selected runtime binaries. SHA-256 values are supported by the existing inventory
collector. The ordinary development profile's source subset alone cannot prove
an installed candidate. Do not edit the retained `expected-profile.json` after
creating a session; its hash is part of the session identity.

```sh
python3 project/tools/device_acceptance.py prepare \
  --profile /private/reviewed-candidate-profile.json \
  --output /private/tg5040-session
python3 project/tools/qualification_review.py template \
  --session /private/tg5040-session --output /private/review-scope-draft.json
```

The template deliberately leaves build, runtime, firmware, filesystem and
installed-file hashes unknown. Fill them from the independently reviewed build,
actual inventory and retained artifacts. Keep the completed scope as a new file.
Changing scope after attempts were recorded makes their old scope digests stale;
a new candidate needs its own baseline and session.

The exact schema-1 scope fields are:

| Field | Contract |
|---|---|
| `schema`, `kind` | `1`, `tg5040-qualification-review-scope` |
| `session_id`, `profile_sha256` | Existing recorder identities; neither may change |
| `candidate` | `frontend_commit` (40 hex); `source_inventory_sha256`, `release_descriptor_sha256`, `package_sha256`, `signer_sha256` (64 hex); pinned `base_commit` and `pyui_tree`; `installed_files` map of exact relative paths to SHA-256 |
| `device` | `model=TG5040`, actual `firmware`, selected `filesystem`; unknown values stay null and block completeness |
| `runtimes` | One to four selected contexts, each with `id`, `engine`, `kind`, `installed_path`, `binary_sha256`, `source_commit`, `source_archive_sha256`, `state_resume` |
| `identity_evidence` | Selected raw references with roles `candidate_package`, `candidate_descriptor`, `candidate_source_inventory` |
| `save_policy` | Exact selected `Saves/` paths mapped to `unchanged` or `gameplay_change_expected`, declared before testing |
| `excluded_features` | Explicit reasons for omitted `native_candidates`, `state_resume` and/or `ports`; a selected feature cannot also be excluded |
| `omitted_runtimes` | Optional `{id,status,reason}` entries; status is `excluded` or `unsupported`, never `pass` |

Runtime `engine` is `ppsspp`, `retroarch` or `port`. Runtime `kind` is
`installed_engine`, `native_candidate` or `port`; ports cannot claim emulator
state Resume. IDs must match `[a-z][a-z0-9_-]{0,31}` and cannot replace reserved
UI context names. Exact binary paths cannot point into ROM, save or BIOS data.
The first core pilot normally keeps the existing installed engines. Selecting
a native candidate adds corresponding-source, appearance, recovery, compatibility
and measured-performance evidence. Source hashes do not replace the separate
R05/R06 permission and distribution reviews.

The source-inventory role consumes the existing packaging
`metadata/release-source.json` shape: `schema`, `descriptor_sha256`, `frontend`,
`source_inventory`, `source_inventory_sha256`. It verifies the clean frontend
commit, selected descriptor and sorted `{path,size,sha256}` rows. The canonical
inventory-list digest differs from the SHA-256 of the JSON file. The raw
reference binds the latter; `candidate.source_inventory_sha256` binds the former.
Installed original module hashes must also match their corresponding source rows.
Package hashing here is a consistency check; package-signature/trust review
remains a separate existing responsibility.

## Record a real observation in the existing chain

Prepare a note template for the selected test and context:

```sh
python3 project/tools/qualification_review.py observation-template \
  --session /private/tg5040-session --scope /private/review-scope.json \
  --case launch_return --test launch_quit --context ppsspp --cycle 1 \
  --output /private/launch-quit-001-draft.json
```

This leaves actual provenance, boot ID, times and raw-file identities null.
Compare any prefilled expected runtime fields against the actual captured target.
Only fill observation fields after performing the reviewed device procedure.
The helper cannot run a game or produce a physical result.

Every structured note has exactly these fields:

```json
{
  "schema": 1,
  "kind": "qualification-observation",
  "scope_sha256": "64 hex: supplied by the template",
  "provenance": "physical_operator OR host_fixture OR static_snapshot",
  "test": "launch_quit",
  "context": "ppsspp",
  "cycle": 1,
  "boot_id": "actual kernel boot UUID",
  "started_at": "actual UTC time with Z or +00:00",
  "ended_at": "later actual UTC time",
  "runtime_sha256": "exact selected binary SHA-256",
  "runtime_source_commit": "exact corresponding source revision",
  "raw": [
    {"path": "relative retained file", "sha256": "64 hex", "scope": "launch_quit"},
    {"path": "relative ownership log", "sha256": "64 hex", "scope": "foreground_ownership"}
  ],
  "state": null,
  "retest_of": null
}
```

The example is a schema illustration, not valid evidence. The generated template
uses the correct scope digest and required evidence roles. UI contexts have null
runtime fields. The bounded compact JSON note must fit the recorder's existing
2,048-character limit. Up to eight explicit raw references are accepted; unknown
fields, free-form authority flags, guessed paths and unlisted tests are rejected.
Raw paths stay relative to the selected private evidence root. Symlinks, special
files, missing/empty files, changed identities, unsafe ancestors and mismatched
hashes are rejected. Files are streamed, with 512 MiB per artifact and 4 GiB per
review hash pass; an oversized selection needs separately scoped evidence.

```sh
python3 project/tools/qualification_review.py record \
  --session /private/tg5040-session --scope /private/review-scope.json \
  --evidence-root /private/tg5040-raw --observation /private/launch-quit-001.json \
  --case launch_return --status pass
```

The command calls `device_acceptance.record()` and appends its normal attempt
record. `fail` and `blocked` use the same immutable chain. A retest keeps the same
test/context/cycle and sets `retest_of` to the previous attempt file's SHA-256 for
that cycle. It never deletes a failure or adds another completed cycle. Legacy
free-text notes remain retained observations, but cannot substitute for detailed
cycle/evidence records.

## Context requirements

| Test | Required context and count |
|---|---|
| `cold_boot` in `boot` | At least ten total, both `classic` and `psp` represented, every counted boot UUID distinct |
| `appearance_switch` in `appearance` | Ten `classic_to_psp` and ten `psp_to_classic` cycles |
| `launch_quit` in `launch_return` | Twenty for each selected runtime, so one engine's count cannot hide another |
| `sleep_wake` in `power_sleep` | Ten for `classic`, ten for `psp`, and ten for each selected runtime |
| `case` | Every applicable one of the recorder's thirteen areas, with the generated context and raw-evidence roles |
| `native_engine` | Each selected native candidate's exact corresponding-source archive, native appearance, performance, recovery and save compatibility |
| `state_resume` | Each selected state-capable runtime's completed write, load acknowledgement, replay rejection, reboot fallback and native config-change evidence |

Cycle indices start at one without gaps. Duplicated cycles and overlapping
intervals within the same test cannot inflate counts. Different contexts have
separate requirements. The launch/sleep policy is intentionally conservative:
the minimum is enforced for every selected runtime. Performance numbers remain
the contents of raw evidence for human assessment; a file hash cannot establish
frame pacing, audio, battery behavior or an improvement.

Ordinary case templates specify the missing detail. Recovery uses distinct
card, overlay and internal-restore artifacts plus retained readback. Input is
checked in both UI contexts. Settings include Undo and writer ownership; USB
includes unmount, return and failed staging; storage includes interruption,
rollback and preservation of newer saves. Each selected port has its own input,
launch/exit, saves, performance and uninstall-preservation scope. Omitted ports
are excluded explicitly; unsupported titles are not passing tests.

State observations additionally contain
`{game_sha256,state_sha256,slot,save_boot_id,load_boot_id}` under `state`.
The two boot IDs must match each other and the observation's boot ID, and the
slot must be an integer from zero to nine. A battery-save hash cannot serve as
state completion or native load acknowledgement. The actual authenticated
engine/foreground/state protocol still needs separate semantic review.

Both before/after recorder captures must contain the same selected battery-save
files. Missing saves block review. An unplanned byte change blocks completeness;
a predeclared gameplay change requires an actual changed hash plus the native
readback evidence. A policy declaration cannot show that a save works. The
proposal retains that interpretation as independent work and never restores an
older save.

## Produce and review a proposal

```sh
python3 project/tools/qualification_review.py review \
  --session /private/tg5040-session --scope /private/review-scope.json \
  --evidence-root /private/tg5040-raw --output /private/review-proposal.json
```

The tool reuses the current [thirteen-area plan](../evidence/device-acceptance-plan.json),
validates the existing recorder's entire snapshot/attempt chains, checks all
selected raw files again after the scan, and rechecks the session. Its report
contains per-context required/attempted/passed counts, retained attempt hashes,
missing/inconsistent observations, explicit exclusions and unsupported titles.
Raw notes, save paths and raw-file contents are not copied into the proposal.

`evidence_structurally_complete` means the declared casebook is consistent and
complete under this policy. Synthetic or mounted-copy evidence remains
`host_or_static_evidence_only`, even if every case has a pass note. Physical
operator labels and live-root snapshot paths are still unverified claims. A
structurally complete physical claim set is only `ready_for_independent_review`.
It does not authenticate the device, operator, measurement or rights evidence.

A reviewer can supply a separate schema-1 `qualification-reviewer-scope` JSON
with `scope_sha256`, the proposal's `casebook_sha256`, opaque `reviewer_sha256`,
an `independent` assertion, `scopes`, `decision` (`accept`, `reject`, `needs_work`)
and an `evidence` raw reference with scope `reviewer_statement`. Required review
scopes are `core` and selected `native:ID`, `resume:ID`, `port:ID` additions.
Pass it using `--reviewer /private/reviewer-statement.json`. The declaration
is reported separately and is not authenticated by this tool. Changing a
snapshot or attempt makes an older casebook declaration stale. A claimed
acceptance cannot repair missing facts, hide a failure or promote a profile.

Every output keeps `hardware_qualified`, `runtime_verified`, `source_use_verified`,
`distribution_cleared`, `automatic_activation` and
`production_configuration_generated` false, with `review_required=true`.
Publication is exclusive, outside the repository/session/raw roots, and flushes
file/directory metadata. A failed publication returns no receipt and leaves
uncertain bytes untouched for inspection. Retain and freshly retrieve the
reviewed artifacts independently; local fsync is not independent-media custody.
