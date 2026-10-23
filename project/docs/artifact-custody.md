# Artifact custody and retrieval

R04 covers exact native outputs, their matching sources/build records and
retrieval from retained storage. Host preview custody is a separate part of the
same task. Neither a stored archive nor a successful cross-build qualifies a
device or clears source-use/distribution terms.

## Retained host previews

The [retention receipt](../evidence/artifact-custody/host-retention.json) records
two private Drive copies. Metadata readback reports owner access and
`shared=false`. Fresh downloads from Drive were checked against independently
recorded GitHub digests. No sharing permissions were added.

| Source | Exact retained artifact | Actual clean CI checkout |
|---|---|---|
| Historical dev9, run `39864873828`, source head `e030677199884441096d90382121b86cfef81796` | ID `12463233054`, 4,836,083 bytes; SHA-256 `a8cfc638853f2030fc5e6561a74bdd80ba9e44c1ab47c8085bc5272e8d29b03e` | `6b4b59cfbdb0597c0dd2c23dea5d904256eeda70` |
| Handover dev9, run `39866632052`, source head `bc80ff272a5c851f3c0dc1ad1832b33ca74148bc` | ID `12464795694`, 4,835,487 bytes; SHA-256 `bf9c5d0bbd1a97d4485b8f937735a17e403257e189530eb62ac67654e7b3a43d` | `9b4dbf050cfd1820e95a57d46131d9538e7fdfcb` |

Both retain successful 690-check certifications, all eight inner checksums,
verified development signatures and 57-file payloads. The actual exported
source bytes match their 150-file inventory SHA-256
`627251e9c22a6b37740b8d3bfd223540969806c4add1deaf33ba6e19402385eb`.
That digest identifies the source inventory; it is not either outer ZIP hash.
The separately retained handover reports preserve its own frontend identity.
Original [third-batch receipts](../evidence/host-batch3/ci-readback.json) remain
unchanged.

Read the file URL/ID from the receipt, fetch its metadata, then retrieve the
complete original ZIP through authenticated Drive. Keep bearer download URLs
out of Git. A local copy can be rechecked without installing or executing its
members:

```sh
python3 project/evidence/artifact-custody/verify-host-artifacts.py \
  /private/retrieved/dev9-e030677-ci.zip \
  --sha256 a8cfc638853f2030fc5e6561a74bdd80ba9e44c1ab47c8085bc5272e8d29b03e \
  --frontend 6b4b59cfbdb0597c0dd2c23dea5d904256eeda70 \
  --source-inventory 627251e9c22a6b37740b8d3bfd223540969806c4add1deaf33ba6e19402385eb
```

Use the corresponding independent values for the handover archive. A digest
calculated from an unknown download cannot authenticate that same download.
The development key shipped inside the archive establishes internal integrity
once the outer bytes are independently identified; it is not an operational
production trust root.

Actions lists expiry on 20 January 2027. The Drive copies preserve retrieval
beyond that temporary artifact window, subject to the owner's storage/account
custody. They are not an irrevocable permanence guarantee. Do not create a
release tag, public release attachment or shared link to retain private native
inputs.

## Native custody remains distinct

The [native retention receipt](../evidence/artifact-custody/native-retention.json)
binds both rebuilt executables, their matching source/build archives and the
new compiler image. All seven files were retrieved from private Drive. The
connector refuses uploads larger than 100 MiB, so larger files use ordered
64 MiB parts; every part and complete reassembled stream was hash-checked.
The receipt records each observed private file ID/URL and exact part order.
R04 is complete for those replacement candidates. Historical binary hashes
remain historical.

Retrieve every part through authenticated Drive without changing sharing. Match
the receipt's part hashes and order, then check the full archive before any
extraction or Docker load. This command only reads the supplied downloads:

```sh
python3 project/evidence/artifact-custody/verify-native-parts.py \
  --manifest project/evidence/artifact-custody/native-retention.json \
  --artifact ppsspp-source \
  /private/downloads/part000 /private/downloads/part001 /private/downloads/part002
```

The source/build archives exclude SDK blobs and owner keys. The separate
compiler image intentionally contains SDK inputs and remains private. Its
saved config/blob identities were independently checked without loading it;
restoration into an empty Docker daemon was not exercised. Docker-save outer
bytes differed across two exports, so only the frozen archive has the recorded
digest. See the independent [source/image review](../evidence/artifact-custody/native-source-review.json)
for exact checks and limits.

The [native recovery status](native-recovery-status.md) and separate
artifact-custody evidence record actual rebuild outcomes and retained native
inputs. Historical PPSSPP/RetroArch hashes and temporary paths alone do not
establish retrieval. A changed binary, archive or compiler image receives a new
record; keep the historical locks and receipts intact.

Keep native executables, complete source/build archives, SDK/compiler images
and private keys out of Git and the original-only host preview. Resolve the
[component review](native-component-review.md) before any native distribution
decision. Physical loading, driver resolution, performance, saves and recovery
remain untested until their device cases run.
