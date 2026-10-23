# PPSSPP notices and source boundary

PPSSPP is Copyright (c) 2012- PPSSPP Project. Modified PPSSPP files retain their
upstream copyright and GPL-2.0-or-later headers. The project native menu extension
and C++ acceptance fixtures are offered under GPL-2.0-or-later. The patch contains
upstream context and project modifications; generated acceptance binaries also
include actual upstream PPSSPP code. The original Python test driver is MIT.
The original Python candidate and FFmpeg builders, checked recipe-application
helper, SDK search preflight and ABI inventory helper are also MIT. Their SPDX
identifiers do not grant rights to
the external source, recipe or SDK inputs they process.

`LICENSE.PPSSPP.txt` is a verbatim copy of upstream `LICENSE.TXT` at
`d357e6a32934800d3d80b49f910a603e1b069751`, including its PSPSDK BSD-compatible
copyright notice and GNU GPL version 2 text. PPSSPP source is available from
https://github.com/hrydgard/ppsspp/tree/d357e6a32934800d3d80b49f910a603e1b069751 .
Project modifications are the adjacent version-pinned patches, with before/after
hashes recorded in `source-lock.json` and, separately, `state-evidence.lock.json`.
The optional completed-state API patch and its C++ acceptance fixture are also
GPL-2.0-or-later. Its Python test driver is original MIT code. The acceptance
build uses the locked upstream SHA-256 implementation, Copyright (C) 2001-2003
Christophe Devine, under its retained GPL-2.0-or-later header. The optional patch
is not included in the earlier native-menu-only candidate or its executable
hash. Its isolated source acceptance does not establish an installed caller;
the later optional state-enabled build has separate exact build evidence.
No compiled PPSSPP binary is distributed
here. A future binary distribution must provide the corresponding source and
applicable upstream and third-party notices for its exact build.

The later private-session caller/export patch, its independently retained
completed-save/load records, its C++ source acceptance fixture,
and the checked spruce save-and-quit adaptation are also GPL-2.0-or-later.
Their locks are `state-session.lock.json` and `recipe-overrides.lock.json`.
The optional full state-enabled candidate includes those exact patches and has
separate build evidence; its binary/source archive remains private. Python
private-session, authenticated capability-transfer and test drivers are original
MIT code. The new extension does not exist in the installed stable emulator.

The separate PowerVR recipe is pinned to
`spruceUI/PPSSPP-spruce@9f770cb984fd8ffcc8f91d24fcbca859439c2e9b`.
That checkout has no root `LICENSE`, and `build-pvr.sh`, `Dockerfile.pvr`,
`patches/common/*.py` and `patches/pvr/*.py` lack an explicit licence grant in
their headers. Those inputs and both SDK archives are retained only in local
build scratch. Recipe and SDK redistribution clearance remains unresolved;
source-retention evidence and a successful compile do not clear a distribution.

The original `psp_shell` Python helpers and original theme assets have their own
license notices. No PPSSPP GPL source is copied into PyUI. The separate spruce
PyUI frontend has its own attribution, noncommercial, and author-notification
terms; this PPSSPP notice does not replace those terms or satisfy notification.
