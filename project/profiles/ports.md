# Owner-data imports and installed port inventory

`ports.json` supplies import contracts for GTA III/VC, Sonic Mania, Render96ex
and Celeste on the original TrimUI Smart Pro. `ports-sources.lock.json` pins
the exact PortMaster launch scripts, metadata and READMEs used for those
contracts, plus the existing spruce PortMaster and PORTS source paths. This
project supplies no engine, runtime, SDK, ROM, commercial data or game download.
San Andreas remains disabled because no verified import/package contract is
established for this target.

`PortsManager.preview_import` inventories owner-selected files, detects FAT
case collisions, validates required structure and checks space before writing.
The Render96 input additionally requires the upstream US ROM MD5 and SHA1.
Apply stages and backs up selected files; failure rolls the copy back. Undo
refuses externally changed imported files. The owner source is never changed.
Profile snapshots/restores own only the listed settings and preserve saves.
The existing PortMaster engine and unrelated installed files remain in place.

`installed_status(port_id)` reads the named owner files, launcher, native
engine alternatives, support artifacts and runtime image from the selected
card. It records SHA256, size and a small header observation for AArch64 ELF
or squashfs inputs. It does not execute or source scripts, mount a runtime,
unpack a package, resolve dynamic dependencies or change permissions. Missing,
empty, unsafe or special files remain explicit observations. Reads use bounded
initial file sizes, nonblocking opens and nofollow directory descriptors, and
refuse files that grow, shrink or change identity while hashing.

| Port | Source-backed installed surface | Remaining interpretation |
|---|---|---|
| GTA III / VC | Classic owner data; `re3` / `re3_gl` or `reVC` / `reVC_gl` | The existing launcher chooses GLES/OpenGL from `glxinfo`; inventory does not choose it. The GTA III README has Vice City copy/paste errors; metadata and the launch script remain separately pinned. |
| Sonic Mania | Owner `Data.rsdk`; installed `sonicmania` | Plus requires the separately documented custom build; no DLC patch or compatibility is claimed. |
| Render96ex | US owner ROM; `sm64.us.f3dex2e.aarch64`; existing resource installer | The first launch extracts resources and can remove the input ROM. An absent original ROM does not prove that an already prepared game is unusable. Its 60 fps default is not a measurement. |
| Celeste | Owner `Celeste.exe` and Content; installed repacker, patches, Mono squashfs | The existing launcher mounts Mono, modifies imported dependencies and repacks copied textures. Keep original owner files separate. Squashfs magic does not qualify Mono or its libraries. |

`portmaster_status()` inventories card-local inputs of spruce's existing
`App/PortMaster/launch.sh`, its control hooks and PortMaster's installed
metadata. Spruce chooses between native `PlatformSpruce` and its compatibility
surface at launch. Presence or a hash never evaluates that Python/shell code.
Other external control folders, running processes, mounts and loader state
remain outside this named-file inventory.

`resolve_existing_port(port_id, backend)` finds the exact installed script in
the existing `PORTS` library and returns `SpruceBackend.resolve_game`'s normal
launch context unchanged. It retains lexical `Emu/PORTS/../../spruce/...`
spelling, per-game controller/governor choices, the existing callback/token,
and Coordinator/resource/process ownership. `resolve_existing_portmaster`
similarly reuses `app:PortMaster`. Read-only backends stay read-only. These
helpers do not create launch permission from file presence or turn inventory
into a second launcher. Existing initialized callbacks and the qualified
runtime remain the only execution authority.

All shipped runtime/distribution flags remain false; frame-rate values remain
null. Exact installed engine/source correspondence, graphics/loader/input/save
compatibility and measured performance require the original-device runbook.
The pinned port text sources identify engines but do not establish their
complete corresponding source or all distribution grants. PortMaster scripts,
engines, support libraries and game assets retain their respective terms;
they are inspected by reference and are not bundled by this feature.
