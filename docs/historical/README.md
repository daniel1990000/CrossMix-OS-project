# Inherited CrossMix release workflow

The [archived workflow](CrossMix%20Release.yml.disabled) is retained byte for byte
from `d02c3c1dddb3670242ca9e9cce7988df0733148e` as historical source. It is outside
`.github/workflows/` and uses a `.disabled` extension, so GitHub Actions cannot
discover or dispatch it. No version tag, including `v*` or a Smart Pro release ID,
can invoke this archived workflow. Removing it from this branch does not change
the workflow on other branches or historical commits; release tags must point
to a revision containing this isolation change.

Do not restore or run this historical packaging recipe. It grants release write
permissions, deletes the inherited root licence and broadly archives the old
CrossMix runtime. Its hardcoded paths are not a security or release boundary.

The active Smart Pro host workflow is
[smartpro-offshoot.yml](../../.github/workflows/smartpro-offshoot.yml). It has
read-only repository permissions, runs host checks and uploads development
artifacts. It does not create GitHub releases or package the inherited root
runtime. The reviewed packaging entrypoints are:

| Entrypoint | Included scope and retained notices |
|---|---|
| `project/tools/build_payload.py` | Explicit project Python/profile/theme/asset folders and extension lists; requires `project/LICENSE` and the Noto Sans OFL; writes original-project, font and dependency notices. |
| `project/packaging/dev_release.py` | Signs that scoped original-only payload and builds the host preview. Its optional source ZIP uses explicit folder/file/extension allowlists, retains the project licence and font notice, and excludes native PPSSPP/RetroArch patches, upstream runtime trees and the unsent notification draft. |

The archived workflow is excluded from both allowlists. These development
artifacts remain host previews; device and native-engine distribution use their
separate qualification and rights records. No tag or release was created to
verify this isolation.
