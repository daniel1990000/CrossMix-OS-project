# RetroArch and spruce IGM source notices

The project modification in `patches/0001-independent-igm-menu-controls.patch`
and the C acceptance fixture in `tests/igm_controls_acceptance.c.in` are
offered under GNU GPL version 3 or, at your option, any later version. They
were added on 22 October 2026 for this TrimUI project. They carry no warranty.
The original Python source-stage/build helpers use the project's MIT licence.

RetroArch v1.22.2, commit
`69a4f0ea1e8aaf442ae4858f2e7f2b31a1776576`, retains its existing contributors'
copyrights, GPL-3.0-or-later terms and component-specific notices. The included
`COPYING` is the unmodified licence document at that source pin, SHA256
`8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903`.
Keep all upstream notices when assembling a private source tree. RetroArch's
licence does not establish the licence of every core, asset or SDK component.

The separately pinned spruce IGM implementation and build recipe are from
`spruceUI/RA` commit `71d84da4dc88945177a3eb34268013355c705dbd`. The inspected
recipe tree has no root licence file, and the IGM C files do not supply an
explicit grant. This notice does not grant rights to that external work.
Corresponding-source, recipe and SDK rights still require clearance before
publishing a complete source archive or candidate binary. Keep those outputs
private while that review remains open. No RetroArch binary, core, driver,
firmware, font or game data is included here.
