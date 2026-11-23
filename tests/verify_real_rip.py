"""Cross-reference verification against a real game rip.

    blender -b --factory-startup --python tests/verify_real_rip.py -- \
        <character.fbx> <report-output.txt>

The test mesh is a real game-character rip (character_mesh, 15,197 vertices,
45 shape keys). Its inventory was taken independently with stock
Blender before this tool existed:

  * 44 keys besides Basis, ZERO of them standard vrc.* visemes
  * blink only as ウィンク / ウィンク右 (+ numbered takes ウィンク２,
    ウィンク２右) — no blink / blink.L / blink.R
  * mouth keys あ・い・お
  * near-duplicate families: にやり x3, Shout/Shout 2, Worry/Worry 2,
    the ウィンク family

The checker report must match that inventory exactly. Then, on a
COPY of the mesh (the original object is never modified), the full
remediation pipeline runs: mirror ウィンク右 -> ウィンク左, apply the
Japanese rename preset, create the remaining visemes, and the final
state is asserted. Prints VISEME_DOCTOR_REAL_RIP: PASS on success.
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from viseme_doctor import core  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("PASS: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILURES.append(label)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    fbx_path, report_path = argv[0], argv[1]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    obj = max(
        (o for o in bpy.data.objects if o.type == "MESH" and o.data.shape_keys),
        key=lambda o: len(o.data.shape_keys.key_blocks),
    )
    print("Test mesh: %s" % obj.name)

    # ---- gate 1: report matches the independent inventory --------
    r = core.analyze(obj)
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(core.format_report(obj, r) + "\n")
    check("vertex count 15197", r["vertex_count"] == 15197,
          "got %d" % r["vertex_count"])
    check("key count 44", r["key_count"] == 44, "got %d" % r["key_count"])
    check("zero visemes present", r["visemes_present"] == [],
          "got %s" % r["visemes_present"])
    check("all 15 visemes missing", r["visemes_missing"] == core.VISEMES)
    check("blink fully missing",
          r["blink"] == {"single": False, "left": False,
                         "right": False, "ok": False},
          "got %s" % r["blink"])
    gap_keys = {g["key"]: g["missing_counterpart"] for g in r["pair_gaps"]}
    check("pair gap is the right wink",
          gap_keys.get("ウィンク右") == "ウィンク左", "got %s" % gap_keys)
    dup_families = [set(g) for g in r["near_duplicates"]]
    check("near-dup: niyari family",
          {"にやり", "にやり２", "にやり３"} in dup_families,
          "got %s" % dup_families)
    check("near-dup: shout family",
          {"Shout", "Shout 2"} in dup_families, "got %s" % dup_families)
    check("near-dup: wink family",
          {"ウィンク", "ウィンク右", "ウィンク２", "ウィンク２右"} in dup_families,
          "got %s" % dup_families)

    # ---- gate 2: remediation pipeline on a copy ------------------
    copy_obj = obj.copy()
    copy_obj.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(copy_obj)
    original_names = list(core.key_names(obj, include_basis=True))

    q = core.mirror_key(copy_obj, "ウィンク右", "ウィンク左")
    print("Mirror quality: %s" % q)
    check("mirror created left wink", "ウィンク左" in core.key_names(copy_obj))
    check("mirror matched >= 80%", q["matched_pct"] >= 80.0,
          "got %.2f%%" % q["matched_pct"])

    renamed, skipped = core.apply_rename(copy_obj, core.PRESETS["japanese_vrc"])
    names = set(core.key_names(copy_obj))
    check("rename produced blink set",
          {"blink", "blink.L", "blink.R"} <= names, "got %s" % sorted(names))
    check("rename produced kana visemes",
          {"vrc.v_aa", "vrc.v_ih", "vrc.v_oh"} <= names)
    check("rename skipped only the absent kana (う, え)",
          {o for o, _n, _w in skipped} == {"う", "え"}, "got %s" % skipped)

    created = core.create_missing(copy_obj)
    check("created the remaining 12 visemes", len(created) == 12,
          "got %s" % created)
    r2 = core.analyze(copy_obj)
    check("copy is fully ready",
          r2["visemes_missing"] == [] and r2["blink"]["ok"],
          "missing=%s blink=%s" % (r2["visemes_missing"], r2["blink"]))
    check("copy key count 57", r2["key_count"] == 57,
          "got %d" % r2["key_count"])

    # ---- gate 3: original untouched -------------------------------
    check("original object untouched",
          core.key_names(obj, include_basis=True) == original_names)

    print("VISEME_DOCTOR_REAL_RIP: %s" % ("FAIL" if FAILURES else "PASS"))
    if FAILURES:
        print("FAILURES: %s" % FAILURES)


if __name__ == "__main__":
    main()
