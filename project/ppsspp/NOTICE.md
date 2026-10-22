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
Project modifications are the adjacent version-pinned patch, with before/after
hashes recorded in `source-lock.json`. No compiled PPSSPP binary is distributed
here. A future binary distribution must provide the corresponding source and
applicable upstream and third-party notices for its exact build.

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
