# Native source coverage completed offline, 23 October 2026

The static work now supplies an actual private source/header/notice packet,
complete asset identities and restored-toolchain provenance. It joins the exact
existing R04 modified engine sources/build records with newly retained source
material. No target binary was executed or selected. Public native redistribution
still needs the specific external grants below and actual installed-loader facts.

The [source package record](../evidence/nondevice-distribution-20261023/final-coverage-source-packages.json)
contains ten downloaded Ubuntu source files: GCC9 cross packaging 21ubuntu7,
GCC9 source 9.4.0-1ubuntu1~20.04.2, cross-toolchain-base 43ubuntu3.2 and
glibc 2.31-0ubuntu9.9. All complete source archives and Debian/Ubuntu patches
match the checksums in their retrieved `.dsc` files. OpenPGP verification and an
independent native rebuild are not claimed. The exact Linaro-declared glibc 2.25
commit source was also retrieved and preserved.

The restored compiler supplied actual startup-object hashes, package controls
and header bytes. The retained RetroArch linker trace explicitly selects Ubuntu
cross-package `Scrt1.o`, `crti.o`, `crtn.o`, GCC9 `crtbeginS.o`/`crtendS.o`,
`libgcc.a`/`libstdc++.a`, and Linaro sysroot nonshared archives. These are now
mapped separately to their source packages and preferred source files. Installed
`Built-Using` confirms glibc 2.31-0ubuntu9.9 for the Ubuntu CRT package. PPSSPP's
implicit default startup selection was reproduced using the same compiler's
`-###` dry driver output; that is labelled reconstruction, rather than an
original retained linker trace. Source-specific runtime exceptions remain in
the preserved source/notice material.

[Actual header source snapshots](../evidence/nondevice-distribution-20261023/final-coverage-headers.json)
retain 2,299 files: 814 GCC9 compiler/C++ headers and 1,485 configured vendor
SDL/EGL/GLES/KHR/ALSA/FreeType/Fontconfig/libudev/V4L2 plus Linaro libc/kernel
interface headers. Exact source releases for SDL 2.26.1, FreeType 2.6.1,
Fontconfig 2.12.1 and ALSA 1.1.4.1 were retrieved, alongside actual SDK headers
with their original notices. Source matches and differences remain visible.
No Qt/WebEngine payload or shared SDK library is bundled. This conservative
source superset preserves preferred header/inline source without pretending
that absent original `.d` dependency files or LTO object membership were retained.

The [native notice material](../evidence/nondevice-distribution-20261023/final-coverage-native-notices.json)
preserves 15,042 source locations and 4,710 distinct complete notice-comment
blocks, including FFmpeg and inline grants. This supplements the earlier 137-entry
review packet; the complete native source archives remain part of the packet set.
Discovery does not infer a grant, and source-specific licence choices still apply.
The private packet supplies the actual material, rather than leaving its assembly
as a future checklist item.

The [debugger record](../evidence/nondevice-distribution-20261023/final-coverage-debugger.json)
resolves deployed commit 9776332 to preferred source commit e47358f. All 632
source-map entries include source content. The full debugger source/lockfile and
36 locked source tarballs covering all 32 bundled package names were fetched;
SHA1 and lockfile integrity checks pass. All package notice material is present,
including the full MIT grant inside `isarray`'s README. The dependency licence
expressions are MIT/BSD-3-Clause, while the debugger declares GPL3-or-later.
No npm installation, package script or target execution was needed.

## Asset provenance and remaining external scope

[All 179 PPSSPP asset files](../evidence/nondevice-distribution-20261023/final-coverage-assets.json),
22,290,281 bytes, match actual public git blobs at the pinned engine/debugger
commits. Every file now has an explicit category, source identity and applicable
notice or remaining source-grant question. This includes 18 PGF fonts, six atlas
files, 41 shader sources, 11 debugger files, ten artwork/vector files, seven sounds,
five TTFs and the remaining configuration/lookup data.

The historical atlas generation scripts were inspected at the exact retained
atlas-change commit d4237fd5. Their original 175,044-byte Roboto-Condensed.ttf
input was retrieved. Its git blob is identical to introduction commit ae17f40e,
whose message explicitly says it is Apache licensed. Preserve Google 2011
copyright and the full Apache 2 text. The absence of an embedded licence string
is therefore not treated as an unresolved grant. The ASCII atlas's recorded
recipe uses that Roboto input. The other historical scripts also name
`ARIALUNI.ttf` and `KozGoPro-Medium.otf`; their bitmap/font terms are separate.
No byte-identical atlas regeneration is claimed.

The current five TTF files have their own exact embedded OFL records. Those
current grants are not retroactively applied to different historical inputs.
PGF names were deliberately camouflaged by an upstream compatibility commit;
Sony-like embedded family strings are not provenance proof. Published Ume-font
contribution/permission statements are recorded for the Japanese font lineage.
They do not establish every later Latin/Korean font input or transformation.

The exact remaining public native questions are:

- Grants for the selected external PPSSPP recipe-generated changes and RetroArch
  IGM additions. Owner-confirmed private noncommercial permission is retained;
  it is not expanded into an unrelated public native grant.
- Exact Arial Unicode/Kozuka bitmap terms and any unresolved PGF source-font
  contribution scope. The actual affected files and historical inputs are now
  identified; permissions are not invented.
- The European emblem's published conditions must be applied to the exact
  proposed branding and support claims, as resolved below. This is an ordinary
  use-condition check; published terms are available and no additional permission
  message is required for compliant use.
- Actual installed loader/library choices and device qualification. These require
  the Smart Pro and are not replaced by a compiler-sysroot inventory.

The [official emblem review](../evidence/nondevice-distribution-20261023/final-coverage-emblem-terms.json)
resolves the earlier direct-download failure. The [Council of Europe](https://www.coe.int/en/web/about-us/the-european-flag)
and [EU legal notice](https://european-union.europa.eu/legal-notice_en) both permit
nonprofit and commercial emblem use under conditions preventing false affiliation,
endorsement or support and unlawful/incompatible activity. The EU expressly says
written permission is unnecessary for compliant use; emblem trademark/IP
registration is not authorized. The exact affected source is the `I_FLAG_EU`
group in `assets/ui_images/images.svg`, with its original acknowledgement retained.
Future branding/support claims must satisfy these conditions. No separate emblem
permission request, author message, blanket CC BY grant or general native
redistribution clearance is inferred.

A separately authored replacement for material lacking a public grant would be
a new candidate with new source/asset identities and functional qualification.
Neither missing external permission nor a successful source-packet retrieval
promotes the existing candidate to public or device-qualified status.

[Private custody/readback](../evidence/nondevice-distribution-20261023/final-coverage-retention.json)
records the complete new supplement and the small historical font/script
supplement, with owner-only sharing, full part/archive hashes and every member's
fresh readback. Existing R04 archives are reused with their exact identities.
The new evidence is later than implementation/build ab644b9 and does not acquire
that build's exported-source inventory identity.
