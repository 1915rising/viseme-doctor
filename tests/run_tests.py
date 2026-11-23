"""Synthetic test suite for Viseme Doctor. Run INSIDE Blender:

    blender -b --factory-startup --python tests/run_tests.py

Builds a symmetric grid mesh with planted shape-key defects (a
spelling variant, a dead key, a .001 duplicate, pair gaps, Japanese
names) and asserts the checker finds every one, then exercises
rename (including the collision-skip path), create-missing and
mirror copy. Prints PASS/FAIL lines and a final sentinel:

    VISEME_DOCTOR_SYNTHETIC: PASS
"""

import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from viseme_doctor import core  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("PASS: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILURES.append(label)


def set_key_deform(obj, name, fn):
    kb = obj.data.shape_keys.key_blocks[name]
    basis = np.empty(len(obj.data.vertices) * 3)
    obj.data.shape_keys.key_blocks[0].data.foreach_get("co", basis)
    pos = basis.reshape(-1, 3).copy()
    verts = [v.co for v in obj.data.vertices]
    for i, co in enumerate(verts):
        pos[i] = fn(co, pos[i])
    flat = np.empty(len(pos) * 3, dtype=np.float32)
    flat[:] = pos.reshape(-1)
    kb.data.foreach_set("co", flat)


def get_key_pos(obj, name):
    kb = obj.data.shape_keys.key_blocks[name]
    arr = np.empty(len(obj.data.vertices) * 3)
    kb.data.foreach_get("co", arr)
    return arr.reshape(-1, 3)


def build_mesh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2.0)
    obj = bpy.context.active_object
    obj.name = "SyntheticFace"

    def add(name, fn=None):
        obj.shape_key_add(name=name, from_mix=False)
        if fn is not None:
            set_key_deform(obj, name, fn)

    add("Basis")  # first key added becomes the reference key
    add("vrc.v_aa", lambda co, p: p + [0, 0, 0.1] if co.y > 0.5 else p)
    add("VRC.V_PP", lambda co, p: p + [0, 0, 0.05])
    add("blink.L", lambda co, p: p + [0, 0, -0.05] if (co.x < -0.5 and co.y > 0.5) else p)
    add("Smile L", lambda co, p: p + [0, 0, 0.03] if co.x < 0 else p)
    add("Smile", lambda co, p: p + [0, 0, 0.03])
    add("Smile.001", lambda co, p: p + [0, 0, 0.04])
    add("DeadKey")
    # shape_key_add copies the active key, so stamp Basis back in:
    # this key must be genuinely identical to Basis.
    basis = get_key_pos(obj, "Basis")
    flat = np.empty(basis.size, dtype=np.float32)
    flat[:] = basis.reshape(-1)
    obj.data.shape_keys.key_blocks["DeadKey"].data.foreach_set("co", flat)
    add("あ", lambda co, p: p + [0, 0, 0.08] if co.y < -0.5 else p)
    add("ウィンク右", lambda co, p: p + [0, 0, -0.05] if (co.x > 0.5 and co.y > 0.5) else p)
    add("wink.R", lambda co, p: p + [0, 0, 0.2 * co.x] if co.x > 0.3 else p)
    return obj


def main():
    obj = build_mesh()

    # ---- analyze -------------------------------------------------
    r = core.analyze(obj)
    check("key count", r["key_count"] == 10, "got %d" % r["key_count"])
    check("visemes present", r["visemes_present"] == ["vrc.v_aa"],
          "got %s" % r["visemes_present"])
    check("visemes missing count", len(r["visemes_missing"]) == 14)
    check("variant detected",
          r["viseme_variants"].get("vrc.v_pp") == ["VRC.V_PP"],
          "got %s" % r["viseme_variants"])
    check("blink state", r["blink"] == {"single": False, "left": True,
                                        "right": False, "ok": False},
          "got %s" % r["blink"])
    check("blink missing", r["blink_missing"] == ["blink.R"])
    check("dead key", r["dead_keys"] == ["DeadKey"], "got %s" % r["dead_keys"])
    flat_dups = [n for group in r["near_duplicates"] for n in group]
    check("near-duplicate .001", "Smile.001" in flat_dups,
          "got %s" % r["near_duplicates"])
    gap_keys = {g["key"] for g in r["pair_gaps"]}
    check("pair gaps", {"Smile L", "ウィンク右", "blink.L", "wink.R"} <= gap_keys,
          "got %s" % gap_keys)

    # ---- mirror --------------------------------------------------
    q = core.mirror_key(obj, "wink.R", "wink.L")
    check("mirror matched 100%", q["matched_pct"] == 100.0, "got %s" % q)
    pos = get_key_pos(obj, "wink.L")
    verts = np.array([tuple(v.co) for v in obj.data.vertices])
    idx_left = int(np.argmin(np.linalg.norm(verts - [-0.6, 0.0, 0.0], axis=1)))
    idx_right = int(np.argmin(np.linalg.norm(verts - [0.6, 0.0, 0.0], axis=1)))
    check("mirror deformation landed on -X",
          abs(pos[idx_left][2] - 0.12) < 1e-4, "z=%f" % pos[idx_left][2])
    check("mirror leaves +X undeformed",
          abs(pos[idx_right][2]) < 1e-6, "z=%f" % pos[idx_right][2])

    # ---- rename (incl. collision skip) ---------------------------
    renamed, skipped = core.apply_rename(obj, core.PRESETS["japanese_vrc"])
    names = set(core.key_names(obj))
    check("rename wink right -> blink.R", "blink.R" in names)
    skip_reasons = {(o, n): w for o, n, w in skipped}
    check("rename collision skipped (あ -> vrc.v_aa)",
          skip_reasons.get(("あ", "vrc.v_aa")) == "target name already exists",
          "got %s" % skipped)
    r2 = core.analyze(obj)
    check("blink ok after rename", r2["blink"]["ok"] is True)

    # ---- create missing ------------------------------------------
    created = core.create_missing(obj)
    check("created 14 visemes", len(created) == 14, "got %s" % created)
    r3 = core.analyze(obj)
    check("all visemes present after create", r3["visemes_missing"] == [])
    check("created keys are genuinely empty",
          set(created) <= set(r3["dead_keys"]),
          "not dead: %s" % (set(created) - set(r3["dead_keys"])))
    check("verdict ready", "READY" in core.format_report(obj, r3))

    print("VISEME_DOCTOR_SYNTHETIC: %s" % ("FAIL" if FAILURES else "PASS"))
    if FAILURES:
        print("FAILURES: %s" % FAILURES)


if __name__ == "__main__":
    main()
