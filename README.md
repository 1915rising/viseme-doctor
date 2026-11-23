# Viseme Doctor

A pre-upload checkup for VRChat avatar shape keys — the check you run
in Blender *before* the avatar reaches Unity, while fixing a name
still costs seconds instead of a re-export.

VRChat matches viseme and blink shape keys **by exact name**. An
avatar can carry a full, well-sculpted set of expressions and still
upload mute and unblinking, because the keys are named in Japanese,
or capitalized differently, or carry a `.001` from a duplicated mesh.
Nothing warns you. In the case that motivated this tool, a game rip
arrived with **44 expression keys — and zero of them under a name
VRChat recognizes**: the blinks were `ウィンク` / `ウィンク右`, the
mouth shapes were `あ・い・お`, and all 15 visemes were missing under
their standard names. The sculpting was done. The naming made it
invisible.

Viseme Doctor finds that class of problem, and fixes the parts that
are safe to fix mechanically: verification, bulk rename, empty-key
creation, and mirror copy with an honest quality report.

## What it checks

| Check | Catches |
|---|---|
| Visemes | All 15 standard `vrc.v_*` keys (sil, pp, ff, th, dd, kk, ch, ss, nn, rr, aa, e, ih, oh, ou), exact-name matching — because that is what VRChat does. |
| Spelling variants | Keys that look like attempts at a viseme (`VRC.V_OH`, `vrc_v_oh`) — reported as variants, and counted as missing, because VRChat will not match them either. |
| Blink | Presence of a single `blink` key or the `blink.L` / `blink.R` pair. |
| Pair gaps | Left/right keys missing their counterpart, across `.L`/`.R`, `_L`/`_R`, ` L`/` R` and `左`/`右` suffix styles. |
| Near-duplicates | Blender `.001` copies and numbered takes (`Shout` / `Shout 2`, `にやり` / `にやり２` / `にやり３`) grouped into families. A clean L/R pair is *not* flagged. |
| Dead keys | Keys whose vertex data is identical to Basis — they deform nothing. |

## What it fixes

- **Bulk rename** from built-in presets (Japanese blink + kana mouth
  names → VRC standard) or your own JSON mapping file. The rename is
  collision-safe: if the target name already exists, that rename is
  skipped and reported, never forced. The reference key is never
  renamed.
- **Create missing keys** as empty keys. Created keys are stamped
  with the Basis positions explicitly (Blender's `shape_key_add`
  otherwise initializes a new key from whichever key is *active*,
  which would make your "empty" viseme a copy of something else).
  Empty means empty: sculpting the shapes is still on you.
- **Mirror copy** of a key across the X axis (`.L` ⇔ `.R`), with a
  vertex-correspondence quality report: how many vertices matched a
  mirrored partner, and the mean/max residual distance. On the test
  rip below: 99.32% of 15,197 vertices matched, mean residual
  0.00016 — and the 104 vertices that did *not* match are reported,
  not silently dropped.

Reports go to the console and to a `VisemeDoctor_Report` text block
in Blender. A real report from the test rip is in
[`examples/`](examples/real-rip-report.txt).

## Requirements

- Blender **4.2 LTS** (developed and tested on 4.2.3).
- No pip installs, no Unity / VRChat SDK. This tool prepares names
  and key data in Blender only.

## Usage

Install `viseme-doctor-1.0.0.zip` (or a ZIP built with
`python3 build_zip.py`) via Preferences > Add-ons > Install, enable
**Viseme Doctor**, select a mesh, and use the **Viseme Doctor** tab
in the 3D Viewport sidebar.

Everything is also drivable headless through the plain Python API —
that is how the test suite exercises it:

```python
import viseme_doctor.core as vd

report = vd.analyze(obj)                    # dict of all findings
print(vd.format_report(obj, report))        # human-readable report
vd.apply_rename(obj, vd.PRESETS["japanese_vrc"])
vd.create_missing(obj)                      # empty keys for the gaps
quality = vd.mirror_key(obj, "ウィンク右", "ウィンク左")
```

## Tests

All tests run inside Blender (background mode is fine):

```bash
# Synthetic mesh with planted defects — variant, dead key, .001
# duplicate, pair gaps, Japanese names — plus rename / create /
# mirror assertions:
blender -b --factory-startup --python tests/run_tests.py

# The shipped ZIP, installed and driven like a user would:
blender -b --factory-startup --python tests/test_install.py -- viseme-doctor-1.0.0.zip

# Cross-reference run against a real rip (paths are arguments):
blender -b --factory-startup --python tests/verify_real_rip.py -- <model.fbx> <report.txt>
```

## Known blind spots (v1, stated on purpose)

- **Shape quality.** Viseme Doctor verifies names and key data, not
  whether the sculpted shape actually reads as the phoneme. A
  perfectly named `vrc.v_aa` can still be a bad "aa".
- **The kana mapping is approximate.** あ→aa, い→ih, う→ou, え→e,
  お→oh is the standard conversion-guide mapping; it fixes naming,
  not phoneme fidelity.
- **Mirror correspondence is positional.** It assumes a roughly
  X-symmetric mesh in object space. Heavily asymmetric or
  re-topologized meshes will show it in the quality report —
  believe the report, not the copy.
- **Unity-side everything**: avatar descriptor setup, eye-look
  configuration, and what VRChat does after upload are out of scope.

## Tested on

Viseme Doctor was validated against a **real game-character rip**
(`character_mesh`, 15,197 vertices, 45 shape keys): the checker's report
matched an independently taken inventory of that mesh exactly —
44 keys, zero standard visemes, blink present only under Japanese
names. The full remediation pipeline (mirror the right wink to
create the missing left, rename from the Japanese preset, create
the remaining 12 visemes as empty keys) was then run on a copy of
the mesh and the final state asserted: 57 keys, 15/15 visemes,
complete blink set, original object untouched. See
`tests/verify_real_rip.py` — that cross-reference is the gate this
tool ships under.

Other rigs and naming conventions are **untested**. Issues and
reports from other avatars are welcome.

## License

MIT — see [LICENSE](LICENSE).
