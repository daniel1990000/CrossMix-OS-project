# Distribution work without a Smart Pro, 23 October 2026

The original-only host preview can continue under its existing MIT/OFL scope.
This work supplies actual reusable native notice material and resolves the
provenance of incorporated glibc objects. R06 remains open for the optional public
native binaries: the exact external recipe/IGM grants, complete selected source
and asset notice coverage, and target loader observations still lack evidence.
No native binary, upstream runtime or SDK is added to the host preview.

The [rights register](distribution-register.json) and [rights summary](release-rights.md)
now reflect the owner's existing R05 confirmation. Private noncommercial source
use is complete for that scope; no further author contact is required. Public
native and SDK terms remain separate. The assistant sent no message.

## Actual notice packet

[Selected native notices](../evidence/nondevice-distribution-20261023/selected-native-notices.txt)
contains 137 exact source-file excerpts or full texts, including GPLv3, LGPL,
Apache, BSD and inline grants, RetroArch filter notices, ImGui/SFMT supplements,
and the full standard OFL text. It has 543,710 bytes and SHA-256
`88463b6395cbb499ffd9448712577062d911df8e21cd08fc1148b811c4409ee4`.
The [manifest](../evidence/nondevice-distribution-20261023/notice-packet-manifest.json)
records each source file's complete hash, selected byte offsets and excerpt hash.
It is a selected review supplement; source-tree dependency notices can be
more inclusive than actual linked code. It does not certify complete notice
coverage or grant distribution clearance.

The [font record](../evidence/nondevice-distribution-20261023/native-font-notices.json)
was regenerated from the five actual TTF name tables in the retained PPSSPP
source archive. It preserves each exact font hash, copyright, OFL declaration
and licence URL. No font binary is copied into this evidence. ImGui and SFMT full
texts were freshly retrieved from the exact primary commits already identified
in the earlier rights review; their supplemental status remains explicit.

The packet was generated twice from freshly retrieved, fully hash-verified
PPSSPP and RetroArch source archives. Packet, manifest and font records match
byte for byte. A corrupt input is rejected before packet publication. These
are replay checks, recorded in [verification](../evidence/nondevice-distribution-20261023/verification.json),
and are not additions to the strict host-suite count.

To replay, place the two exact R04 source archives at `ppsspp-source.tar.gz`
and `ra-source.tar.gz` in a private directory, together with `imgui-LICENSE.txt`,
`sfmt-LICENSE.txt` and `glibc-COPYING.LIB`. The latter three inputs have their
required hashes enforced by the replay script. Their primary locations are:

- [ImGui full MIT text at 993fa347](https://github.com/ocornut/imgui/blob/993fa347495860ed44b83574254ef2a317d0c14f/LICENSE.txt).
- [SFMT full BSD text at 2b820223](https://github.com/MersenneTwister-Lab/SFMT/blob/2b8202239c90d0b21c6125070d76ca44c70342be/LICENSE.txt).
- [glibc LGPL text at a0408ec5](https://github.com/bminor/glibc/blob/a0408ec51ea862dda102482036c401d2e707e20b/COPYING.LIB).

```sh
python project/evidence/nondevice-distribution-20261023/replay_notice_packet.py \
  /private/exact-native-inputs /private/replayed-notices
```

The complete downloads remain outside Git. The
[fresh retrieval receipt](../evidence/nondevice-distribution-20261023/fresh-retrieval.json)
binds both source archives and both build-record archives to the existing R04
complete hashes after every retained part was checked. This reuses R04 custody;
it does not count it again as a completed task.

## Incorporated glibc source identity

The exact vendor SDK archive, SHA-256 `b6b615d03204e9d9bb1a91c31de0c3402434f6b8fc780743fa88a5f1da6f3c79`,
contains neither `libc_nonshared.a`, `libpthread_nonshared.a` nor libc startup
objects. The build's sysroot is seeded by copying the retained Linaro libc tree
before applying vendor `usr/include` and `usr/lib` overlays. The nonshared
objects must therefore be tracked as toolchain runtime material, separately
from the vendor SDK headers and dynamic libraries.

The 213,977,008-byte Linaro archive was freshly retrieved and matches R04
SHA-256 `604d97c1f5fadc88d6ebff577ea648d0fbc650411af98a3bd8783dbe4e3ed154`.
Its embedded `gcc-linaro-7.5.0-2019.12-linux-manifest.txt` identifies glibc
`release/2.25/master` at commit `a0408ec51ea862dda102482036c401d2e707e20b`.
The full source at that commit was retrieved: 28,193,321 bytes, SHA-256
`c8d491a68591b5a7ad548d56068eda407ec00b77bcdb70355addf182a1b006b1`.
The primary `COPYING.LIB` is now included in the review packet.

The [object/source map](../evidence/nondevice-distribution-20261023/incorporated-libc-source-map.json)
records all 16 members of `libc_nonshared.a` and the one member of
`libpthread_nonshared.a`, each object hash, its DWARF compile-unit source path,
and the matching manifest-commit source file hash and notice. This is producer
manifest plus actual object metadata evidence. It does not claim a byte-identical
recompile or that every archive member survived final linking. Complete startup,
header and Ubuntu GCC runtime source coverage still needs the exact final native
source-delivery packet. A blanket SDK licence is unnecessary for unbundled code;
applicable incorporated code obligations still apply.

## Boundaries for the remaining native work

The core frontend can use the existing installed engines through their existing
launch and menu authorities. A package that distributes only the original
frontend and original settings/theme data does not thereby redistribute those
engine binaries, recipe code or vendor libraries. This bounded host/overlay
scope does not close R06 for the optional replacement-engine programme. Actual
core execution and public device delivery still require D02–D06.

The retained replacement PPSSPP contains GPLv3-or-later libkirk and Apache
components. A future combined native release must use a compatible GPLv3 route
and retain each component's terms; describing the entire binary as GPLv2-only
would be wrong. The separate original Python remains MIT.

Public native release remains blocked on the exact PPSSPP recipe-generated
changes and external RetroArch IGM source grant; no new grant was found or
inferred. The new packet also does not settle all FFmpeg component notices,
all native artwork/shader/data provenance, exact final RetroArch incorporated
membership, or complete source-delivery obligations. Those are named residual
work, independent of claims about physical qualification. Replacing external
changes with independently authored implementations would require new native
builds and functional qualification; excluding them is not counted as completion.
Actual installed loader/system-library observations require the Smart Pro.

All runtime selectors and production/profile/source-use gates remain disabled.
No target binary ran, no owner data changed, and no public native distribution
was performed.
