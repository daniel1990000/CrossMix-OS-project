# Independent spruce in-game menu controls

The optional source patch adds a separate Confirm/Back preference to spruce's
actual RetroArch in-game menu (IGM). It retains the existing raw joypad poll,
gameplay remaps, D-pad/slot actions and delayed close until both A/B buttons
are released. The standard RetroArch menu remains a separate surface; changing
`menu_swap_ok_cancel_buttons` does not configure the IGM.

The recipe pin and exact input/output hashes are in `source-lock.json`.
`spruceUI/RA` at that pin builds upstream RetroArch v1.22.2. Its
`patches/common/0001-spruce-igm.patch` contains the real IGM; its
`common_src/spruce_igm_theme.c` reads the active JSON configuration at the
first IGM initialization. The added namespace is opt-in:

```json
"project_menu_controls": {
  "enabled": true,
  "confirm": "south",
  "back": "east"
}
```

Both complete pairs are supported. Absent, disabled, malformed, nested or
incomplete values preserve legacy IGM behavior: raw libretro A confirms and
B closes. In the source contract, B is south (`0`) and A is east (`8`). The
installed controller correspondence still needs original-TG5040 acceptance.
The added project keys do not alter any gameplay button assignment.

Apply the project patch after the recipe's common patches and common source
copy, as the full builder documents in `build-candidate.md`. The narrow
`source_patch.py` helper stages only the three IGM files for host acceptance:

```sh
python3 project/retroarch/source_patch.py \
  --recipe-root /path/to/untouched/spruce-ra \
  --output /private/new-igm-stage
SPRUCE_RA_SOURCE_ROOT=/path/to/untouched/spruce-ra PYTHONPATH=project \
  python3 -m unittest discover -s project/tests -p 'test_spruce_igm_*.py' -v
```

The compiled host harness uses actual patched parser callbacks, raw poll,
key resolver and action handler with narrow service fixtures. It verifies
defaults, both conventions, malformed values, parser nesting, held release,
D-pad/state-slot behavior and input lockout. It does not compile a whole
RetroArch engine or exercise RJSON event delivery, rendering or physical
joypads. `source-lock.json` records that source-stage scope; any separate
full-engine build has its own command log, source manifest, binary hash and
SDK report.

`EmulatorConfigAdapter` supports this namespace only through an explicit
qualified extension profile and a trusted `active_theme_config` observer.
It edits the same global or current-theme file selected by the existing
IGM source precedence and preserves palette/layout/unknown fields. The
appearance adapter separately edits supported color keys. Both reuse the
existing journal/generation/writer gates; share their state directory and
maintenance authority if used together. Strict JSON is editable; JSONC is
refused unchanged to preserve comments.

The bundled spruce v4.5.4 `RetroArch/ra64.universal` was observed read-only as
14,850,952 bytes, SHA256
`bd96dd8f10c479d17ff4a5db943a6828ccb0b74c6eb463faeb99d941fa16d550`.
Its embedded `1.22.2` and IGM strings do not prove exact source correspondence.
It has not been replaced, and the shipped profile remains unqualified. See
`NOTICE.md` before publishing any complete source or binary output.
