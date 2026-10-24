# Dev16 host merge and publication

PR #1 is merged into `main` at `87264629735e179c81c2ad360516665c1e7fd5cd`.
The owner's explicit merge/publication instruction supersedes the earlier
host-software draft hold. All device/profile gates remain disabled.

[The dev16 computer preview is published](https://github.com/daniel1990000/CrossMix-OS-project/releases/tag/smartpro-host-0.1.0-dev16).
Its tag and attached matching source select `99336f6525efbd1b790a15c7de54acca3eacd1ec`.
The 223-file original-source inventory is
`a0c9c9179528ddc0e9316a6aef2bda9c6f4d4ef24f70c91296d49c18a6ea834a`;
the signed payload has 66 files. Runtime fixes remain those from `a8ba317`.
The later documentation in the public snapshot changes its source inventory;
earlier local/CI receipts retain their exact separate hashes.

Source/provenance run [40041273891](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/40041273891)
passes all 1,099 strict checks against five pinned sources, zero skips, errors
or failures. Merge CI 40041238422 passes. Delivery run
[40042094364](https://github.com/daniel1990000/CrossMix-OS-project/actions/runs/40042094364)
passes host checks, provenance and the selected delivery job. All ten host
subjects pass cryptographic workflow/source provenance verification. Every
uploaded file was read back before publication; all eleven public assets were
freshly downloaded afterward and match the receipt and provider SHA256 values.
A no-Git source export reproduces both release ZIPs byte for byte and passes
installed smoke/fixture rollback. Generated development keys were deleted.

The shell could create the draft but its artifact redirect and upload credential
routes were unavailable. The connected artifact downloader supplied verified
bytes. The existing Actions publication route completed delivery with its
job-scoped token. The added dev16 input defaults false and requires manual
invocation plus host success; contents write permission is limited to delivery.
It binds the exact dev16 packet to the retained verifier/publisher. The historical
dev14 helper, tag, release and all eleven asset IDs/sizes/digests are unchanged.

The attached original-source ZIP is the matching source for this preview.
GitHub's automatic repository archives include inherited mixed source/runtime
and historical engines, outside this verified attached scope. The attached
files exclude native engine patches/binaries, SDKs, games, saves and private
keys. MIT/OFL/dependency notices remain included. Existing private native
build/compiler custody and source-use permission records are preserved.

[Verification](../evidence/host-publication-20261023/verification.json),
[publication receipt](../evidence/host-publication-20261023/publication-receipt.json),
[public readback](../evidence/host-publication-20261023/public-readback.json) and
[no-Git rebuild](../evidence/host-publication-20261023/no-git-rebuild.json)
record the exact outcomes. Later main/workflow/evidence/docs commits have their
own source identity and do not change the fixed public tag or attached bytes.

The register remains 14/25 complete and 0/13 physical areas run. Actual Smart Pro
recovery/inventory, qualification, five matched game-scene runs and 30-minute
sustained runs for demanding profiles remain pending. Candidate presets remain
untested and unavailable figures remain unavailable. Precise public native
terms, production signing/custody and accepted maintenance ownership remain
open. This host publication supplies no device qualification or production
trust root. State galleries, named save history and power-off Resume remain
later enhancements. No author message was sent.
