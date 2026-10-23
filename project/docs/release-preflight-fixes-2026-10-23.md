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
