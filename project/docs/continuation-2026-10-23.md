# Ten engineering steps, 23 October 2026

This batch adds ten host engineering items from D01, D03, R06, O01 and O03.
They advance five open master-plan rows. The plan still has **12 of 25 completed
host tasks**, and **zero of 13 physical areas tested**. Device entry/action
wiring, actual backup/restoration and runtime observations, notification scope,
component rights and operational key custody remain open.

| Item | Plan row | Added behavior |
|---|---|---|
| 1 | D01 | Independent expected candidate/file hashes and fresh boot/principal identity checks for a synthetic host case |
| 2 | D01 | Typed, single-use admission with startup expiry, replay rejection and owner-thread checks |
| 3 | D01 | View-only action policy rejecting launches, settings/favorites writes, Resume, USB and power transitions |
| 4 | D01 | Monotonic return request and restoration deadlines; late or partial restoration cannot permit classic return |
| 5 | D01 | Principal timeout observation retains subreaper ownership through real `ECHILD` and refuses completion after expiry |
| 6 | D01 | Redacted, bounded, fsynced event journal with hash chaining, fresh readback and poisoned-writer behavior after failure |
| 7 | D03 | Read-only copied-root/live-host inventory with exact tool/helper identities and isolated kernel probes |
| 8 | R06 | Component/custody audit joining engine/recipe identities and five actual patch hashes; seven pinned primary-source files reviewed |
| 9 | O01 | Disposable signing-key rotation, retirement, revocation and recovery rehearsal through existing package APIs |
| 10 | O03 | Local upstream metadata comparison that queues changes for review without fetching, executing candidate code or updating pins |

The admission factory accepts synthetic host observations only. Its expected
hashes must come from an independent review; the helper does not verify a
package signature or prove the origin of those hashes. There is no fixed
experimental device entry. The principal observation policy is optional and
unwired in shipped configuration. Cooperative checks cannot interrupt a blocked
renderer, input call or evidence write. All existing production gates remain
closed.

## Verification

Clean source/build commit: `0585e1de62b1e38b291a96eed7793464c4f272e1`.
The strict five-source check passes **833 tests**: 772 host/source and 61 PPSSPP,
with zero skips, failures, errors or expected failures. There are 123 new checks
across the six work lanes. [CI run 39877124999](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39877124999) also passes all 833 on clean merge `71d2c19dcdaa78782ccfaa98c464801c00dd98a5`; its complete artifact and exported source pass [fresh readback](../evidence/continuation-20261023/ci-readback.json). See [the retained verification](../evidence/continuation-20261023/verification.json).

The original-only `smartpro-psp-0.1.0-dev11` build verifies its development
signature, 59-file payload, same-key determinism, installed-payload SDL/settings/
navigation smoke and fixture rollback. Its 177-file original-source inventory
has SHA-256 `179b85ec30396c3031431fe59da0a588fe9311d717f8350c622c994e2ca04df9`.
Rebuilding its exported source without Git reproduces both ZIPs byte for byte.
Generated signers were deleted; signatures from different generated keys are
not claimed identical. No native binary or upstream patch is selected.

Independent review found and fixed hook/filter execution in Git inspection,
replace-ref ambiguity, missing-file handling, unsafe failed-output cleanup,
disposable-process timeout/identity gaps and unjoined component hashes. The
journal also rejects same-size content changes. Failed upstream-report writes
retain uncertain bytes and never delete a replacement pathname. Regression
tests preserve these cases.

The final upstream comparison finds **230 changed paths within the configured
integration scopes** and **374 outside** between pinned spruce v4.5.4 and the
previously inspected Development revision `cb6210aa19c5cb61e404d4029444972448cac9f9`.
The report is a review queue. No source pin, patch or installed runtime changed.

## Next work

Finish the fixed experimental entry and bind real actions/stop requests at the
existing principal and embedded owners. Activation still requires actual R05
delivery/scope evidence, D02 backup retrieval/restoration rehearsal and D03
observed original-device readiness. The new tools do not supply those facts.
Native admissions also need the exact retained R04 artifacts and applicable
R06 review. Keep operational key custody and update/requalification decisions
separate from the disposable host exercises.

No original TG5040 was connected or probed. No author was contacted. Existing
engines, firmware and owner data remain unchanged. No device performance,
battery, physical recovery or Resume durability result is claimed. PR #1 remains
draft and unmerged.
