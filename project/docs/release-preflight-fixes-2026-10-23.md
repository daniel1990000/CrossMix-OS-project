# Dev16 release preparation fixes

This continuation starts at handover `2d4a43d` and preserves the completed dev15
work. Hardware remains unavailable. Three reproduced host defects were fixed:

- Gameplay `record` and `compare` output could replace input documents or raw
  observations after validation. Both commands now reject colliding paths,
  including resolved aliases, sustained runs and unselected observation files.
- Five-pair comparisons could combine different run durations, observation
  windows or allowed measurement methods across pairs. All five repeats now
  require one duration and one method/window per selected metric.
- A PS1 disc-reference parent or final path could become an outside-card symlink
  after containment validation. Reads and availability checks now walk resolved
  components through held directory descriptors without following swapped
  symlinks. Existing symlinks that resolve within the card remain supported.

The regression checks use synthetic host fixtures. Their failures on historical
code describe newly added checks; they do not change dev15's retained 1,092-check
result. The focused suites pass 23 gameplay and 17 game-information checks. A
separate read-only review confirms those results, existing symlink compatibility
and stable descriptor counts through 1,000 repeated inspections.

The current development descriptor selects `smartpro-psp-0.1.0-dev16`. Exact
certification, packaging and CI results belong in
[this continuation's verification](../evidence/release-preflight-20261023/verification.json).
The existing five-source runner, original-only packager and installed smoke/
rollback checks are reused. Native code and retained native builds are unchanged.
The public dev14 download and dev15's historical artifacts retain their identities.

The register remains 14/25 complete with 0/13 physical areas run. Device/profile
gates stay disabled and PR #1 stays draft and unmerged. Recovery/inventory,
physical qualification, five matched game-scene runs and 30-minute demanding
profiles remain pending. Candidate presets remain untested; unavailable gameplay
figures remain unavailable. Precise public native distribution decisions,
production signing/custody and accepted maintenance ownership remain open.
Permission records are preserved and no author message was sent.

## Verified snapshots

Clean local implementation/build `a8ba3176e78d248162d3d40b91ec1d8b854491a9`
passes **1,099 strict checks** (1,038 host/source plus 61 PPSSPP), zero skips,
failures or errors against all five pinned references. Packaging verifies the
66-file signed payload, installed SDL/navigation/game-info/filter/backup smoke,
fixture rollback and same-key determinism. Both ZIPs match the no-Git export
rebuild byte for byte. The 223-file source inventory is
`5058e82140dc25e5d0b7ff429845b90566865cd804e25b92078192f953fcbd4d`.
Disposable signers were deleted; development signing supplies package integrity.

[CI 39926662133](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/39926662133)
passes all 1,099 checks on clean PR merge
`933a1a5367552804cca8a78725e4c87779f9ce9b`. Artifact `12490006540` was
downloaded and fully verified against the provider's SHA256:
`96a1426c9201e8b3f27e57d531e6476c702a264749ebe6c4fa5cc6785bdc8c9a`,
5,246,728 bytes. All eight checksums, signature/payload and 223 source files
pass readback. Expiry is 21 January 2027; independent owner-storage retention
was not performed for this checkpoint.

Later documentation/evidence changes have their own frontend/source identity.
The exact clean build inventory and package hashes above stay bound to their
recorded local and CI snapshots. Historical native serialization evidence is
unchanged and does not qualify custom callbacks, Resume or Smart Pro gameplay.
