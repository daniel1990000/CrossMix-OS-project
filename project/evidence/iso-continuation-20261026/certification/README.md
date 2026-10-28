# Host certification and package evidence

The baseline checkout at `30aa59ffa35195bcad2b2553f91c43fc32301556` passed 1,209 strict tests with zero skips, errors or failures.

The first changed-tree run attempted 1,213 tests and failed two UI compatibility checks. Its report, log and input hashes are retained as `final-attempt1-*`. Review found that the initial launch-capability guard also hid independently authorized Game options. The correction preserves that route and updates the private view-only test to check both the hidden UI action and direct dispatcher rejection.

The final changed-tree run passed all 1,213 tests with zero skips, errors or failures and a successful host preview render. Its ten changed/new file hashes exactly match clean implementation commit `a962d6c9d213f9d76b6a104ba78a282029cc453a`; `final-receipt.json` records that binding. The test itself ran immediately before the commit, and is not relabeled as a clean-checkout run.

Packaging used a separate clean detached checkout of that implementation. Dev19 has 68 signed payload files and 236 original-source inventory entries. Signature, payload/source inventory, all eight output checksums, installed smoke, fixture activation/rollback and same-key deterministic overlay checks passed. Both ZIPs rebuilt byte for byte from the exported source without Git. Each build deleted its generated development private key.

`review.json` records independent UI and optional GPU-stats source reviews. The optional native patch's exact function-body ASan/UBSan tests reproduce the original float-buffer overflow and validate the correction. This receipt does not establish a complete patched native engine or device result. The original-only preview does not select or distribute that native patch or any emulator/game/state binary.

Build and certification UTC intervals are retained for correlation with concurrent host workloads. No gameplay performance conclusion comes from these checks. No physical qualification, production profile activation, public release or published dev16 change occurred.

Only sanitized source/test/build metadata and host logs are retained here. Paths name temporary execution workspaces, not durable artifact storage. Generated signatures use disposable development identities; their public verification does not establish production custody. Game data, native saves/states, full downloaded distributions and private keys remain excluded.

`ci-readback.json` independently verifies retained CI run 40383733188: the provider ZIP digest, all eight inner checksums, development signature, 68 payload files, source-to-payload correspondence and 1,213 passing tests. CI built clean PR merge `d25f46b3d731a4ea623ecfec2da798cc3fe41ebe`, whose parents are the implementation and newer main metadata. Its exported source differs from the local implementation package only in `docs/master-plan-2026-10-22.md`; embedded build identity also differs. These are separately identified packages.
