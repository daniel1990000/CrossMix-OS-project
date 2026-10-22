# Native component review

R06 remains open. This review adds a [component ledger](native-component-ledger.json)
for the historical PPSSPP state-session and RetroArch/IGM candidates. It separates
build tools, incorporated code, target libraries and adjacent assets. It records
no author contact, distribution clearance or device qualification.

The starting checkpoint is `bc80ff272a5c851f3c0dc1ad1832b33ca74148bc`.
The historical PPSSPP binary is `a93f7db82692c4b95dcb15282d8d73080d51a8912fc8e435adb3b6dfe30c165d`;
the RetroArch binary is `118146e2aed90c5ccbc416e4c7e01acc8ec7abb7462e1d43f97e8734f113df1d`.
R04 handles retrieval or rebuilding of those private outputs and matching archives.
Any rebuild with different bytes needs a new record. The historical hashes stay fixed.

## Findings from pinned sources

| Scope | Observed evidence | Work still required |
|---|---|---|
| Build tools | Original builders use MIT. The recorded native builds use GCC 9 cross tools, CMake, Git, Python and Docker. | Retain exact package/source versions and generated commands. Separate runtime/header code incorporated by compilation from the compiler executable. |
| Spruce PPSSPP recipe | The complete pinned tree has 53 blobs and no licence-named files. The reviewed README, build files and ten selected source-edit scripts provide no explicit grant. | Resolve terms for the scripts and generated source modifications. The script's build-time execution does not settle the licence of text it inserts into the engine. |
| Spruce IGM/RA recipe | The complete pinned tree has 89 blobs and no licence-named files. Reviewed build files, four selected patches and three shared IGM sources provide no explicit grant. | Resolve the external IGM/shared-source and recipe scope separately from upstream RetroArch and the project's GPL modification notice. |
| FFmpeg | The recorded five static libraries come from `1e3b4965632f60b1d85360261d1b9dd45444bc71`. Its generated configuration reports LGPL-2.1-or-later with GPL, nonfree and version-3 switches disabled. | Retrieve/rebuild matching sources, archives, headers and commands; review the applicable combined-executable distribution route and per-file notices. |
| GCC runtime | Both build records select static `libstdc++.a` SHA-256 `c6e9d9e3a4965a811e3281aa593a14d3d6c56897ee2e62812eae9fb1ac2f1c4d`. GCC 9.4.0 terms identify GPLv3 plus Runtime Library Exception 3.1 for covered files. | Map the exact Ubuntu cross package and incorporated code to its source/notices and exception conditions. Upstream release terms alone do not prove Ubuntu package correspondence. |
| Embedded components | Pinned source selects shader/compiler, compression, disc, image, audio and other targets. Some component terms appear inside headers. | Recover actual compile/link membership and review each incorporated component. Preserve licence-version choices and compatible obligations for the resulting combination. |
| SDK and target libraries | The pinned PPSSPP README calls vendor SDKs proprietary. The release description supplies no additional grant. Historical ELF audits cover 16/23 SDK objects. | Inspect per-component SDK terms and incorporated headers/startup objects. Actual installed library/driver identity belongs to D03. Review any library proposed for bundling as an exact separate input. |
| Native assets | The PPSSPP recipe copies its whole `assets/` tree, including fonts, shaders, UI data and a debugger gitlink. | Inventory selected asset bytes and terms. The original frontend's MIT/OFL scope does not establish terms for these native assets. |

The tree observations apply to these exact revisions:

- [PPSSPP recipe `9f770cb`](https://github.com/spruceUI/PPSSPP-spruce/tree/9f770cb984fd8ffcc8f91d24fcbca859439c2e9b).
- [RA/IGM recipe `71d84da`](https://github.com/spruceUI/RA/tree/71d84da4dc88945177a3eb34268013355c705dbd).
- [GCC 9.4.0 runtime exception](https://github.com/gcc-mirror/gcc/blob/13c83c4cc679ad5383ed57f359e53e8d518b7842/COPYING.RUNTIME).

No licence-named file in a tree does not prove that a grant cannot exist elsewhere.
The exact grant remains unresolved in the reviewed material. Do not infer terms
from another repository's root licence or from public download availability.

## Notice coverage gaps to close during R04

The historical PPSSPP record retains 55 named notice files. That list includes
`Common/UI/Notice.cpp`, test-only material and empty nested `build/LICENSE` files.
It also omits inline terms such as
[`ext/libpng17/png.h`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/ext/libpng17/png.h)
and [`ext/xbrz/xbrz.h`](https://github.com/hrydgard/ppsspp/blob/d357e6a32934800d3d80b49f910a603e1b069751/ext/xbrz/xbrz.h).
Use the complete source and actual link membership to review component scope;
counting filenames cannot establish notice completeness.

The pinned FFmpeg [licence summary](https://github.com/hrydgard/ppsspp-ffmpeg/blob/1e3b4965632f60b1d85360261d1b9dd45444bc71/LICENSE.md)
identifies IJG-derived JPEG sources and executable-documentation credit.
[`jfdctfst.c`](https://github.com/hrydgard/ppsspp-ffmpeg/blob/1e3b4965632f60b1d85360261d1b9dd45444bc71/libavcodec/jfdctfst.c)
gives the wording: “this software is based in part on the work of the Independent JPEG Group”.
The historical configuration enables MJPEG decoding/encoding. The pinned configure
dependencies select IDCTDSP for MJPEG decoding, and the codec Makefile includes
`jrevdct.o` under IDCTDSP. Confirm incorporated members with the rebuilt archives
and final link; retain the applicable credit and source change record. This review
does not assert that a prior distributed binary omitted a required credit.

The pinned glslang licence contains multiple component terms, while SPIRV-Cross
uses Apache-2.0. Review the GPL version selected for the actual combination and
retain applicable notices. RetroArch's disabled Vulkan flag also does not prove
absence of shader/compiler code: its historical build records report bundled
SPIR-V/glslang warnings. Generated configuration and link membership decide scope.

## Validation and next evidence

The review fetched 38 pinned source files/excerpts through read-only GitHub tools.
All 21 fetched recipe inputs that have checked-in lock entries match their SHA-256
digests. The ledger records Git blob IDs, source URLs and hashes of returned UTF-8
text; excerpt hashes identify only the returned lines. The recipe tree responses
were untruncated. No native executable ran during this review.

Next, pair each R04 binary with retrievable complete source/build archives and
actual component membership. Retain per-component notices and resolve the exact
recipe/IGM/SDK scope before a distribution decision. R05 notification delivery,
commercial permission where relevant, and physical acceptance remain separate
requirements. Keep PR #1 draft and shipped runtime/profile/source-use gates false.

Related records: [release rights](release-rights.md),
[continuation review](continuation-rights-review.md),
[PPSSPP build evidence](../evidence/ppsspp-complete-state-build.json),
[RetroArch build evidence](../evidence/retroarch-igm-build.json).
