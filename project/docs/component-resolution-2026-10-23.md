# Exact native notices and source resolution, 23 October 2026

The R06 review now uses freshly retrieved R04 source/build archives and the
actual recorded native link inputs. [The evidence](../evidence/completion-20261023/native-rights-review.json)
contains archive/part hashes, complete source-inventory digests, selected-file
hashes, native notice candidates, package provenance and the original-only
payload manifest. This advances the component review; it does not certify a
native binary for public distribution or execution.

The owner confirms that the authors were already notified and gave permission.
That statement supports continued private noncommercial source integration. It
is owner-confirmed evidence, not correspondence inspected by this review.
Nothing was sent by this work. Exact public redistribution terms for external
recipe/IGM code and SDK components are a separate scope; the general permission
statement is not silently expanded into those terms. Physical qualification is
also separate and remains unrun.

## Retrieved and inspected bytes

Both source archives were freshly fetched from the owner-only Drive parts,
every part hash checked, reassembled in order and checked against the complete
R04 digest. Both build-record archives were independently fetched and checked.
No archive was installed and no target binary ran.

| Artifact | Complete SHA-256 | Size |
|---|---|---:|
| PPSSPP corresponding source | `2575f85be69acab16a6e4b015dda72f3e13b355b3609894fc3d58b059ae18556` | 177,963,111 bytes |
| PPSSPP build records | `ba2e68c6d0d5e0101f1f8491e4330ab93475b6aec1216ef2a514fa20154384d1` | 291,510 bytes |
| RetroArch corresponding source | `61e03dde636297a5dc6556464513c6d22a063113e4327be82637aa755c9b2f36` | 144,576,907 bytes |
| RetroArch build records | `70d1cb17690cd78a74f08e9f1efe8d03048d58499e75e7470c648f0e58a05446` | 595,274 bytes |

The new [notice inventory tool](../tools/notice_inventory.py) hashes complete
regular files, records links without following them, and inventories named
notice candidates. It scans bounded header prefixes as a discovery aid. It
does not extract files, execute code, infer licences or claim corresponding-
source completeness. Duplicate/traversal paths, changed archives, special
files and size/count overruns fail. Inline terms can occur beyond its prefix:
Lua's actual licence is at the end of `ext/lua/lua.h` and was inspected
separately. Generated `*.js.LICENSE.txt` is recognized; `Notice.cpp`, empty
`build/LICENSE` files and unrelated tests cannot be treated as licence coverage.

```sh
PYTHONPATH=project python project/tools/notice_inventory.py \
  /private/path/candidate-corresponding-source.tar.gz \
  --expected-sha256 2575f85be69acab16a6e4b015dda72f3e13b355b3609894fc3d58b059ae18556
```

## PPSSPP: actual link inputs and notice sources

The retained final `PPSSPPSDL` link command names **37 distinct static archive
inputs**, including five FFmpeg archives. This is actual recorded link selection,
not a conclusion drawn from a root CMake target alone. Archive selection does
not prove that every archive member survived dead stripping/LTO. The earlier
IJG defined-symbol evidence separately establishes that selected JPEG code
survived in the recorded unstripped output.

The exact source below is present in the retrieved source archive; complete
file hashes and any supplemental upstream text are retained in the evidence.

| Linked scope | Exact notice source | Resolved observation / release treatment |
|---|---|---|
| Engine and original project patches | `LICENSE.TXT` and retained project notices | Engine/project scope is GPL-2.0-or-later; PSPSDK notice and other components retain separate terms. |
| libkirk | `ext/libkirk/kirk_engine.c` | Explicit **GPL-3.0-or-later**. A future combined binary must use a compatible GPLv3-or-later route; do not describe it as GPL-2.0-only. This does not relicense unrelated Python/PyUI code. |
| Basis Universal and SPIRV-Cross | `ext/basis_universal/basisu_transcoder.cpp`, `ext/SPIRV-Cross/LICENSE` | Apache-2.0 notices are retained. Their combination also needs a compatible GPL version and applicable notices/change statements. |
| libzip | `ext/libzip/zip.h` | Full BSD-style three-condition source/binary notice appears in the header; it was absent from filename-only lists. |
| Vulkan Memory Allocator | `ext/vma/vk_mem_alloc.h` | Full AMD MIT grant appears inline, including copyright and notice retention. |
| Lua | End of `ext/lua/lua.h` | Full MIT grant, Lua.org/PUC-Rio copyright; preserve it despite absence of a separate licence-named file. |
| xxHash | `ext/xxhash.h` | Full BSD-2-Clause notice, including binary documentation condition. |
| standalone ATRAC decoders | `ext/at3_standalone/atrac3.cpp` and adjacent source headers | LGPL-2.1-or-later code is linked independently of the five FFmpeg archives. Retain its own source/notice obligations too. |
| gason, CityHash, rcheevos, armips | Their retained `LICENSE`/`COPYING` files | MIT-style grants and notices are available in the exact source. |
| Snappy, udis86, libchdr, Zstandard | Their retained `COPYING`/`LICENSE` files and nested libchdr dependencies | BSD-style notices; Zstandard has a dual-licence choice. Choose and record the applicable route and retain nested terms. |
| libpng17 and xBRZ | `ext/libpng17/png.h`, `ext/xbrz/xbrz.h` | Inline libpng conditions and xBRZ GPL/special MAME exception are preserved. The MAME exception is not a general permission to combine with any frontend. |
| minimp3 | `ext/minimp3/minimp3.h`, `minimp3_ex.h` | Public-domain dedication/CC0 references and warranty statements are present in both included headers. |
| ImGui | `ext/imgui/imgui.cpp` | Source identifies standard MIT and Omar Cornut copyright, but points to missing `LICENSE.txt`. Upstream v1.91.6 full MIT text was retrieved at `993fa347495860ed44b83574254ef2a317d0c14f` as an explicitly labelled supplement; preserve the fork's exact copyright too. |
| SFMT | `ext/sfmt19937/SFMT.h`, `SFMT.c` | Source expressly identifies BSD-3-Clause and points to missing `LICENSE.txt`. The official licence text at `2b8202239c90d0b21c6125070d76ca44c70342be` was retrieved as a supplement; it does not establish byte-identical source correspondence. |
| glslang and cpu_features | Their retained aggregate licence files | Multiple component notices remain applicable. An aggregate licence filename is not one licence for every compiled file. |

Before native publication, create the actual combined notices packet from
these texts, preserve modifications and the chosen GPL/LGPL route, and review
the remaining recipe/header/runtime scope below. Supplemental upstream texts
are not represented as files already present in the old R04 archive.

## Exact GCC runtime package provenance is now resolved

The R04 build selected static `libstdc++.a` SHA-256
`c6e9d9e3a4965a811e3281aa593a14d3d6c56897ee2e62812eae9fb1ac2f1c4d`.
The exact published Ubuntu package
`libstdc++-9-dev-arm64-cross_9.4.0-1ubuntu1~20.04.2cross2_all.deb`
was retrieved from build `24568796`. Its `.deb` matches the SHA-256 in the
build's published `.changes`; the extracted archive is **byte-identical** to
the linked R04 static archive. This closes the earlier uncertainty about which
binary package supplied that library.

Launchpad identifies source package `gcc-9-cross`, version `21ubuntu7`. The
matching `gcc-9-cross-base` package's 75,285-byte copyright file was fetched and
hashed. It expressly lists `libstdc++-v3` and covered libgcc/runtime material
under GPLv3-or-later plus GCC Runtime Library Exception 3.1, and includes the
complete exception. Its additional permission depends on covered files and an
eligible compilation process. Exact package identity resolves provenance; it
does not extend the exception to independent external source or prove every
startup/header component's scope. Published checksums were checked; an OpenPGP
signature validation is not claimed.

## Assets and RetroArch are separate scopes

The PPSSPP archive contains the full 179-file, 22,290,281-byte `assets/` tree,
including the recursive debugger output. All five font files' actual TTF name
tables identify **SIL Open Font License 1.1**: Inconsolata and all four Roboto
Condensed variants. Preserve their exact embedded copyright records and supply
the applicable full OFL text with future font redistribution; do not assume
Roboto is Apache-licensed from its name. The debugger's
`assets/debugger/static/js/main.fe87e942.js.LICENSE.txt` is retained and hashed.
Other artwork/shader/data provenance still requires its per-file review.

RetroArch's generated configuration explicitly enables built-in mbedTLS,
glslang, FLAC, compression and static filters despite disabling Vulkan. Exact
mbedTLS `aes.c` carries Apache-2.0; the inspected glslang header carries its
BSD-style conditions. Actual source hashes and retained aggregate notices are
recorded. The available selected link trace proves the GCC/static startup and
SDK library inputs but is not a complete per-object link map. It must not be
labelled one. Review the enabled filters/other incorporated files and produce
the full binary notice packet before public distribution.

## Small remaining source/SDK questions, with preservation options

These questions are narrower than a blanket request to redistribute a whole
SDK or an operating system:

1. **PPSSPP recipe-generated code:** the exact ten selected scripts at
   `spruceUI/PPSSPP-spruce@9f770cb` and their generated postimages are listed in
   the evidence. The retained material gives no explicit file-level grant for
   that external inserted text. For public binary/source publication, retain
   applicable terms covering those exact changes. If those terms remain
   unavailable, independently implement the documented behaviours as a new,
   reviewed GPL patch set and rebuild/requalify; do not silently drop cursor,
   pause/control, safe quit or PowerVR compatibility behaviour.
2. **External IGM additions:** review the exact selected recipe patches and
   `spruce_igm`/platform/theme source at `spruceUI/RA@71d84da`. A project GPL
   modification notice does not establish the external source grant. An
   independently authored in-engine implementation would be a separate scoped
   replacement requiring equivalent functional/device qualification. The core
   interface can still use the existing installed engine and its maintained
   native menu while optional replacement engines remain unselected; this is
   the plan's staged delivery, not completion of the optional engine work.
3. **Incorporated SDK/startup material:** the exact 185,049,621-byte TG5040 SDK
   was fetched and matched `b6b615d0…da6f3c79`. Selected `usr/include/SDL2`
   headers contain zlib-style terms; selected `EGL`, `GLES2` and `KHR` headers
   contain MIT-style Khronos grants. The build also records
   `libc_nonshared.a`, `libpthread_nonshared.a`, GCC runtime/startup objects and
   associated headers. Finish the exact source/notice mapping for those
   incorporated objects. The SDK metadata scan found no standalone blanket
   grant. Its unrelated Qt/WebEngine payload is not a selected engine
   dependency and must not be bundled merely because it appears in the SDK.
4. **Unbundled target libraries:** SDL/GLES/EGL and other recorded shared
   dependencies are expected on the device; no replacement dynamic libraries
   are selected for the public package. A blanket SDK redistribution permission
   is unnecessary for the original-only host payload, which contains no SDK.
   A future bundled library receives its own exact byte/source/terms review.
   Actual installed loader choices and any system-library assessment still
   require D03 observations.

The original-only dev11 baseline was independently inventoried: 60 preview
files and 178 source-export files, with exact MIT notice, OFL notice and Noto
font-byte comparisons. Neither ZIP contains a native ELF. The evidence includes
the complete per-file manifest. This is a concrete notice check of those exact
archives, not a statement that it certifies a future changed package. Repeat
the inventory on the final newly built artifacts.

All complete source/native/SDK/package downloads and extracted inspection bytes
remain in private scratch, outside Git and host previews. The repository saves
hashes, paths, classifications and evidence only. The 12 focused inventory tests
cover unsafe/duplicate paths, links, special files, bounds, archive changes,
notice false positives, generated suffix notices and deterministic file
inventories across ZIP and TAR.
