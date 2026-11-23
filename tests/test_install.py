"""Install test: install the built ZIP like a user would, enable it,
and drive its operators. Run INSIDE Blender:

    blender -b --factory-startup --python tests/test_install.py -- <zip>

Prints VISEME_DOCTOR_INSTALL: PASS on success.
"""

import sys

import bpy

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("PASS: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILURES.append(label)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    zip_path = argv[0]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
    bpy.ops.preferences.addon_enable(module="viseme_doctor")
    check("add-on enabled", "viseme_doctor" in bpy.context.preferences.addons)

    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.active_object
    obj.shape_key_add(name="Basis", from_mix=False)
    obj.shape_key_add(name="ウィンク", from_mix=False)

    check("check operator runs",
          bpy.ops.viseme_doctor.check() == {"FINISHED"})
    check("report text block written", "VisemeDoctor_Report" in bpy.data.texts)

    check("rename operator runs",
          bpy.ops.viseme_doctor.rename(preset="japanese_vrc") == {"FINISHED"})
    names = [kb.name for kb in obj.data.shape_keys.key_blocks]
    check("operator rename worked", "blink" in names, "got %s" % names)

    check("create operator runs",
          bpy.ops.viseme_doctor.create_missing() == {"FINISHED"})
    names = {kb.name for kb in obj.data.shape_keys.key_blocks}
    import viseme_doctor.core as core
    check("all visemes created by operator",
          all(v in names for v in core.VISEMES))

    print("VISEME_DOCTOR_INSTALL: %s" % ("FAIL" if FAILURES else "PASS"))


if __name__ == "__main__":
    main()
