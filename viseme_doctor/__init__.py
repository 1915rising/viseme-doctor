"""Viseme Doctor — VRChat viseme / shape key checker for Blender.

Free and open source (MIT). Checks a mesh's shape keys against the
15 standard VRChat visemes and blink keys, renames keys in bulk from
presets or a custom JSON mapping, creates missing keys as empty
keys, and mirror-copies a key across the X axis with a vertex
correspondence quality report.

All functionality is also available headless through
``viseme_doctor.core`` — see the README.
"""

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator, Panel

from . import core
from .presets import PRESETS, PRESET_LABELS

bl_info = {
    "name": "Viseme Doctor",
    "author": "1915rising",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Viseme Doctor",
    "description": "Verify, rename, create and mirror VRChat viseme "
                   "and blink shape keys",
    "category": "Mesh",
}


def _active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    return obj


class VISEMEDOCTOR_OT_check(Operator):
    bl_idname = "viseme_doctor.check"
    bl_label = "Check Shape Keys"
    bl_description = "Verify visemes, blink, duplicates, dead keys and pair gaps"

    def execute(self, context):
        obj = _active_mesh(context)
        if obj is None:
            self.report({"ERROR"}, "Select a mesh object first")
            return {"CANCELLED"}
        result = core.analyze(obj)
        core.write_report_text_block(obj, result)
        self.report(
            {"INFO"},
            "Visemes %d/%d, blink %s — full report in text block "
            "'VisemeDoctor_Report'"
            % (len(result["visemes_present"]), len(core.VISEMES),
               "ok" if result["blink"]["ok"] else "missing"))
        return {"FINISHED"}


class VISEMEDOCTOR_OT_rename(Operator):
    bl_idname = "viseme_doctor.rename"
    bl_label = "Bulk Rename"
    bl_description = "Rename keys from a built-in preset or a custom JSON mapping"

    preset: EnumProperty(
        name="Preset",
        items=[(key, PRESET_LABELS[key], "") for key in sorted(PRESETS)]
              + [("custom", "Custom JSON file", "")],
        default="japanese_vrc",
    )
    custom_path: StringProperty(
        name="Custom mapping (JSON)",
        subtype="FILE_PATH",
        description="JSON object of {old_name: new_name}; used when "
                    "Preset is 'Custom JSON file'",
    )

    def execute(self, context):
        obj = _active_mesh(context)
        if obj is None:
            self.report({"ERROR"}, "Select a mesh object first")
            return {"CANCELLED"}
        if self.preset == "custom":
            if not self.custom_path:
                self.report({"ERROR"}, "Choose a custom mapping JSON file")
                return {"CANCELLED"}
            mapping = core.load_mapping(self.custom_path)
        else:
            mapping = PRESETS[self.preset]
        renamed, skipped = core.apply_rename(obj, mapping)
        for old, new, why in skipped:
            self.report({"WARNING"}, "Skipped %s -> %s (%s)" % (old, new, why))
        self.report({"INFO"}, "Renamed %d keys, skipped %d"
                    % (len(renamed), len(skipped)))
        return {"FINISHED"}


class VISEMEDOCTOR_OT_create_missing(Operator):
    bl_idname = "viseme_doctor.create_missing"
    bl_label = "Create Missing Keys"
    bl_description = "Create missing viseme/blink keys as empty (Basis-copy) keys"

    def execute(self, context):
        obj = _active_mesh(context)
        if obj is None:
            self.report({"ERROR"}, "Select a mesh object first")
            return {"CANCELLED"}
        created = core.create_missing(obj)
        self.report({"INFO"}, "Created %d keys: %s"
                    % (len(created), ", ".join(created) or "none needed"))
        return {"FINISHED"}


class VISEMEDOCTOR_OT_mirror(Operator):
    bl_idname = "viseme_doctor.mirror"
    bl_label = "Mirror Copy Key"
    bl_description = "Copy a shape key across the X axis with a quality report"

    source: StringProperty(name="Source key", default="blink.R")
    target: StringProperty(name="Target key", default="blink.L")

    def execute(self, context):
        obj = _active_mesh(context)
        if obj is None:
            self.report({"ERROR"}, "Select a mesh object first")
            return {"CANCELLED"}
        try:
            quality = core.mirror_key(obj, self.source, self.target)
        except KeyError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Mirrored %s -> %s: %.2f%% vertices matched (mean residual %s)"
            % (self.source, self.target, quality["matched_pct"],
               quality["mean_residual"]))
        return {"FINISHED"}


class VISEMEDOCTOR_PT_panel(Panel):
    bl_idname = "VISEMEDOCTOR_PT_panel"
    bl_label = "Viseme Doctor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Viseme Doctor"

    def draw(self, context):
        layout = self.layout
        obj = _active_mesh(context)
        if obj is None:
            layout.label(text="Select a mesh object", icon="MESH_DATA")
            return
        layout.label(text=obj.name, icon="MESH_DATA")
        layout.operator("viseme_doctor.check", icon="VIEWZOOM")
        layout.separator()
        layout.label(text="Bulk rename:")
        layout.operator("viseme_doctor.rename", icon="SORTALPHA")
        layout.operator("viseme_doctor.create_missing", icon="ADD")
        layout.separator()
        layout.label(text="Mirror copy:")
        layout.operator("viseme_doctor.mirror", icon="MOD_MIRROR")


CLASSES = (
    VISEMEDOCTOR_OT_check,
    VISEMEDOCTOR_OT_rename,
    VISEMEDOCTOR_OT_create_missing,
    VISEMEDOCTOR_OT_mirror,
    VISEMEDOCTOR_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
