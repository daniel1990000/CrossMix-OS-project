# Private source integration and qualification

`project/integration/release.py` supplies the application path for the pinned
spruce fixes and reviewed frontend seams. It produces a separate, private tree
with exact source preimages, patches, resulting hashes, retained upstream
licences and restoration copies. It does not write the inspected source, a
mounted card, firmware, internal startup files or user saves.

The existing original-only overlay format remains separate. A supplied overlay
must pass its existing Ed25519 signature, payload-inventory and source-scope
verifier with an external trusted public key. A development signature does not
establish source-use clearance or hardware qualification.

## Prepare a review kit

This command requires no derivative-source approval. It retains the four
existing review patches and licence notices, records the exact pinned source
files, and lists outstanding release evidence. It applies no patch:

```sh
PYTHONPATH=project python3 -m integration.release prepare \
  --source-root /path/to/untouched-spruce-v4.5.4 \
  --output /tmp/smartpro-release-review
PYTHONPATH=project python3 -m integration.release verify /tmp/smartpro-release-review
```

To retain an independently verified original overlay, add `--overlay PATH` and
`--public-key PATH`. Verification of that kit must receive the external public
key again. The kit does not supply its own trust key.

`--include-state-session` also retains the separately locked PPSSPP wrapper
patch. It is off by default. Selecting it adds the scoped state-session
arguments to the reviewed source plan; it does not activate a profile or
replace the installed emulator.

Every output directory must be new and outside the source tree. Preparation is
private and all-or-none: a failed source, patch or signature check leaves no
published output. Exact input fingerprints are checked again before
publication. A modified source tree, symlink, special file, changed patch or
missing licence is rejected.

## Assemble reviewed source in a new tree

`assemble_private_candidate` is a trusted Python API. It requires a
`SourceUseReview` object that refers to retained notification delivery or
applicable permission and an actual review of its scope. It accepts neither a
JSON profile nor a CLI `true` switch as that decision. Constructing the object
does not send notification, obtain permission or validate legal obligations.
The host tests use explicit fixture decisions; those are not real clearance.

The API applies all four locked spruce patches to private copies and verifies
their exact intermediate results. The selected bridge mode then applies one
reviewed source integration. `process-exit` is the complete process-boundary
seam; `retained-tasks` is the older alternative. They must never be combined.
`none` assembles only the reliability fixes.

The process-boundary mode requires an original signed overlay containing its
runtime modules. It expands that verified payload only inside the new candidate
at `tree/App/PSPMode/integration/`. The source patch contains the fixed literal
module root `/mnt/SDCARD/App/PSPMode/integration/app`. Saved metadata cannot pick
an import path or executable callback. A stale overlay missing a required
runtime module is rejected. The separately reviewed runtime configuration still
defaults to unavailable and cannot be qualified by the development signer.

Each source change records its exact before and after SHA-256, and each patch
has its own retained hash. Python source is compiled for syntax; shell scripts
receive `sh -n`. These checks are source acceptance, not semantic or physical
device qualification. The source caller/principal tests provide separate
semantic host evidence.

`include_state_session=True` additionally applies the separate PPSSPP wrapper
lock after the four reliability patches. Its source and patch hashes are
checked before application, and its exact intermediate result is checked
before the bridge patch is applied. The principal supplies the state request
through its scoped command environment.

## Verify and restore a private candidate

The manifest covers the complete artifact inventory. Verification rejects
changed source, backups, patches, licence notices, added files and attempted
hardware/runtime/distribution qualification. Its checksum detects corruption;
it is not a production publisher signature.

Restoration also creates a new output. It refuses later edits rather than
overwriting them, and keeps the original candidate intact:

```sh
PYTHONPATH=project python3 -m integration.release restore-private \
  /path/to/private-candidate --output /tmp/smartpro-restored-source
```

The restored tree contains the exact retained source preimages. A retained
original overlay requires its external verification key. This operation is
source restoration only. It cannot restore a whole card, internal launcher,
boot scene, vendor firmware or newer user save.

## External evidence remains explicit

The manifest always leaves device activation, hardware qualification, runtime
verification and distribution clearance false. It lists source-use review,
actual source/process/input ownership, installed device identities, save/load,
recovery, power/USB and redistribution evidence separately. No CLI operation
installs, activates, publishes, launches an emulator or turns those fields true.

Run physical acceptance on a spare/restorable original TG5040 before producing
an installation package or enabling the corresponding profile. Keep the private
candidate, exact recipe and source evidence available for that review. The
source application/restoration mechanism is complete independently of those
external observations; it does not substitute for them.

## Composed host acceptance

The `test_composed_candidate_source_principal_state_store_and_next_source_resume`
acceptance assembles the signed original payload, exact source patches and optional state-session
wrapper into the fixed application layout. Separate processes import the
candidate's actual runtime and state modules. The test executes the transformed
Miyoo handoff, waits for detached descendants through the real Linux child
subreaper, authenticates the exact source closure, invokes the patched PPSSPP
wrapper, records an authenticated save capability, and starts a fresh source process that selects the real typed
Resume action and receives a matching load acknowledgement. It also checks
that an inherited state-session environment cannot select the request.

The staged DeviceCommon WiFi mutator also uses the real authenticated relay.
Its explicit shared-service fixture leaves descendants under the principal's
relay while both source and game subtrees finish. The test observes their
actual adopted parent, then lets them exit naturally and requests the real
authenticated relay drain. The relay exits after kernel `ECHILD`. Source closure
does not claim that these independent services stopped.

The source owners, ROM, native state serializer, platform controls and emulator
are explicit host fixtures. This acceptance proves the composed software
route and its lifetime and capability checks. It supplies no physical device,
PPSSPP serializer, recovery or distribution qualification, and leaves every
candidate qualification flag false.
