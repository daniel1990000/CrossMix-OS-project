# Dev18 host evidence

The exact local implementation is `399a528542da1139903c93cef3041d23acad2fca`.
[Verification](verification.json) links the 1,209-check strict certification,
clean build, source inventory, installed smoke, fixture rollback and no-Git ZIP
rebuild. [CI readback](ci-readback.json) independently verifies the downloaded
artifact against its provider digest, expected merge/source identity, signed
payload and matching source export. CI includes the separate main-branch audit
document; it has a different source identity from the local implementation.

- [Review ownership and corrections](review.json) and [independent integration review](independent-integration-review.json).
- [Final strict certification](certification.json) and [full log](certification.log).
- [Build report](build-report.json), [source inventory](release-source.json), [checksums](SHA256SUMS) and [no-Git comparison](no-git-rebuild.json).
- [Starting baseline](baseline-certification.json) and [rejected first candidate](candidate-rejected-certification.json). The rejected run is deliberately retained and is not passing evidence.
- [144-render matrix](render-matrix.json), [18 actual UI workflows](workflow-review.json) and [26 retained representative PNGs](retained-renders.json).
- [Public dev16 identity check](published-identity-check.json); this checks tag/provider metadata and does not claim a new download of all public asset bytes.

The matrix covers six text sizes, both Confirm positions, both contrast modes
and library/dialog/empty/loading/error/keyboard states. `matrix.py` and
`workflows.py` retain the actual capture scripts, including the temporary roots
used for this run. They require the project's Python/SDL dependencies and
`PYTHONPATH=project`; adjust their temporary/project roots when reproducing in
another checkout. Runtime source hashes are recorded beside capture hashes.
Only the PNGs listed in `retained-renders.json` are committed; all 144 matrix
outputs were generated and representative states inspected.

The workflow uses 70 independently registered synthetic offline payloads,
reaches entry 65, renames/cancels correctly, performs real background byte
verification and checks that source and payload bytes remain unchanged. No
commercial game, user save, private key or device data is retained here.

Independent reviewers were separate AI-agent lanes. Focused check counts
overlap and are not added together. Only `certification.json` gives the complete
unique suite count. Device/profile gates remain disabled, 0/13 physical areas
have run, and these records establish no device performance, battery, physical
recovery or Resume reliability.
