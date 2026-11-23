"""Core logic for Viseme Doctor.

Everything here takes a Blender mesh object and works through the
plain Python API, so the whole tool can be driven headless:

    import viseme_doctor.core as vd
    report = vd.analyze(obj)
    print(vd.format_report(obj, report))
    vd.apply_rename(obj, vd.PRESETS["japanese_vrc"])
    vd.create_missing(obj)
    quality = vd.mirror_key(obj, "wink.R", "wink.L")

Checks performed by analyze():
  * the 15 standard VRChat visemes, exact-name matching (VRChat
    matches names exactly, so a spelling variant counts as missing
    and is reported separately as a variant);
  * blink keys: VRChat accepts a single ``blink`` key or the
    ``blink.L`` / ``blink.R`` pair;
  * near-duplicate key families (Blender ``.001`` copies and numbered
    takes such as ``Shout`` / ``Shout 2``);
  * dead keys (vertex data identical to Basis);
  * left/right pair gaps across the common suffix styles
    (``.L``/``.R``, ``_L``/``_R``, `` L``/`` R``, ``左``/``右``).
"""

import json
import re
import unicodedata

import bpy
import numpy as np
from mathutils import kdtree

from .presets import PRESETS  # noqa: F401  (re-exported for convenience)

VISEMES = [
    "vrc.v_sil", "vrc.v_pp", "vrc.v_ff", "vrc.v_th", "vrc.v_dd",
    "vrc.v_kk", "vrc.v_ch", "vrc.v_ss", "vrc.v_nn", "vrc.v_rr",
    "vrc.v_aa", "vrc.v_e", "vrc.v_ih", "vrc.v_oh", "vrc.v_ou",
]

BLINK_SINGLE = "blink"
BLINK_L = "blink.L"
BLINK_R = "blink.R"

# (suffix, side, counterpart suffix) — counterpart uses the same style.
_SIDE_SUFFIXES = [
    (".L", "L", ".R"),
    (".R", "R", ".L"),
    ("_L", "L", "_R"),
    ("_R", "R", "_L"),
    (" L", "L", " R"),
    (" R", "R", " L"),
    ("左", "L", "右"),
    ("右", "R", "左"),
]

_DEAD_EPS = 1e-6


# ---------------------------------------------------------------- names

def key_names(obj, include_basis=False):
    """Shape key names on a mesh object ([] when it has none).

    The reference key (index 0, usually named "Basis") is excluded
    unless include_basis — in Blender, index 0 is always the
    reference, whatever it happens to be named.
    """
    if obj is None or obj.type != "MESH" or not obj.data.shape_keys:
        return []
    names = [kb.name for kb in obj.data.shape_keys.key_blocks]
    if not include_basis and names:
        names = names[1:]
    return names


def _normalize(name):
    """Loose form for variant detection: NFKC, lowercase, alnum only."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", name).lower())


def _viseme_variant_candidates(missing_viseme, names):
    """Existing names that look like attempts at a missing viseme."""
    target = _normalize(missing_viseme)            # e.g. "vrcvaa"
    bare = _normalize(missing_viseme.split(".")[-1])  # e.g. "vaa"
    code = missing_viseme.rsplit("_", 1)[-1]        # e.g. "aa"
    out = []
    for n in names:
        norm = _normalize(n)
        if norm in (target, bare) or norm == "vrc" + code or norm == code:
            out.append(n)
    return out


def _split_side(name):
    """(base, side, counterpart_name) or (name, None, None)."""
    for suffix, side, other in _SIDE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            base = name[: -len(suffix)]
            return base, side, base + other
    return name, None, None


def _family_base(name):
    """Core name with side suffix and trailing numbering stripped.

    Used to group near-duplicate families: にやり / にやり２ / にやり３
    all reduce to にやり; ``Shout`` / ``Shout 2`` reduce to ``Shout``.
    """
    base, _side, _other = _split_side(name)
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[\s.]*\d+$", "", base)
    return base


def _has_number_suffix(name):
    base, _side, _other = _split_side(name)
    return bool(re.search(r"\d\s*$", unicodedata.normalize("NFKC", base)))


# ---------------------------------------------------------------- data

def _key_positions(obj, key_block):
    n = len(obj.data.vertices)
    arr = np.empty(n * 3, dtype=np.float64)
    key_block.data.foreach_get("co", arr)
    return arr.reshape(n, 3)


def _dead_keys(obj, eps=_DEAD_EPS):
    if not obj.data.shape_keys:
        return []
    blocks = obj.data.shape_keys.key_blocks
    basis = _key_positions(obj, blocks[0])
    dead = []
    for kb in blocks[1:]:
        pos = _key_positions(obj, kb)
        if pos.shape == basis.shape and float(np.abs(pos - basis).max(initial=0.0)) <= eps:
            dead.append(kb.name)
    return dead


# ---------------------------------------------------------------- analyze

def analyze(obj):
    """Run every check on a mesh object. Returns a plain dict."""
    names = key_names(obj)
    name_set = set(names)

    present = [v for v in VISEMES if v in name_set]
    missing = [v for v in VISEMES if v not in name_set]
    variants = {}
    for v in missing:
        cands = _viseme_variant_candidates(v, names)
        if cands:
            variants[v] = cands

    blink = {
        "single": BLINK_SINGLE in name_set,
        "left": BLINK_L in name_set,
        "right": BLINK_R in name_set,
    }
    blink["ok"] = blink["single"] or (blink["left"] and blink["right"])
    blink_missing = []
    if not blink["ok"]:
        if blink["left"] != blink["right"]:
            blink_missing.append(BLINK_R if blink["left"] else BLINK_L)
        else:
            blink_missing.append(BLINK_SINGLE)

    # Near-duplicate families: .001 copies outright, plus families
    # that carry numbered takes. A clean L/R pair is not a duplicate.
    near_duplicates = []
    for n in names:
        if re.search(r"\.\d{3}$", unicodedata.normalize("NFKC", n)):
            near_duplicates.append([n])
    families = {}
    for n in names:
        families.setdefault(_family_base(n), []).append(n)
    for base, members in sorted(families.items()):
        if len(members) > 1 and any(_has_number_suffix(m) for m in members):
            near_duplicates.append(sorted(members))

    pair_gaps = []
    for n in names:
        _base, side, counterpart = _split_side(n)
        if side and counterpart not in name_set:
            pair_gaps.append({
                "key": n,
                "side": side,
                "missing_counterpart": counterpart,
            })

    return {
        "object": obj.name if obj else None,
        "vertex_count": len(obj.data.vertices) if obj else 0,
        "key_count": len(names),
        "all_keys": names,
        "visemes_present": present,
        "visemes_missing": missing,
        "viseme_variants": variants,
        "blink": blink,
        "blink_missing": blink_missing,
        "near_duplicates": near_duplicates,
        "dead_keys": _dead_keys(obj) if names else [],
        "pair_gaps": pair_gaps,
    }


def format_report(obj, result=None):
    """Human-readable report (also written to a Blender text block)."""
    if result is None:
        result = analyze(obj)
    lines = []
    lines.append("Viseme Doctor report — %s" % result["object"])
    lines.append("Mesh: %d vertices, %d shape keys (excluding Basis)"
                 % (result["vertex_count"], result["key_count"]))
    lines.append("")
    lines.append("VISEMES: %d/%d present"
                 % (len(result["visemes_present"]), len(VISEMES)))
    for v in VISEMES:
        mark = "ok     " if v in result["visemes_present"] else "MISSING"
        lines.append("  [%s] %s" % (mark, v))
    if result["viseme_variants"]:
        lines.append("")
        lines.append("SPELLING VARIANTS (count as missing — VRChat "
                     "matches names exactly):")
        for v, cands in sorted(result["viseme_variants"].items()):
            lines.append("  %s <- looks like: %s" % (v, ", ".join(cands)))
    lines.append("")
    b = result["blink"]
    lines.append("BLINK: %s (blink=%s, blink.L=%s, blink.R=%s)"
                 % ("ok" if b["ok"] else "MISSING: " + ", ".join(result["blink_missing"]),
                    b["single"], b["left"], b["right"]))
    if result["pair_gaps"]:
        lines.append("")
        lines.append("LEFT/RIGHT PAIR GAPS:")
        for gap in result["pair_gaps"]:
            lines.append("  %s has no counterpart %s"
                         % (gap["key"], gap["missing_counterpart"]))
    if result["near_duplicates"]:
        lines.append("")
        lines.append("NEAR-DUPLICATE KEYS:")
        for group in result["near_duplicates"]:
            lines.append("  %s" % " / ".join(group))
    if result["dead_keys"]:
        lines.append("")
        lines.append("DEAD KEYS (identical to Basis, no deformation):")
        for n in result["dead_keys"]:
            lines.append("  %s" % n)
    lines.append("")
    ok = (not result["visemes_missing"] and b["ok"]
          and not result["pair_gaps"] and not result["dead_keys"])
    lines.append("VERDICT: %s" % ("READY — all visemes and blink present"
                                  if ok else "NOT READY — see above"))
    return "\n".join(lines)


def write_report_text_block(obj, result=None):
    """Write the report into a Blender text block and return the text."""
    text = format_report(obj, result)
    block = bpy.data.texts.get("VisemeDoctor_Report")
    if block is None:
        block = bpy.data.texts.new("VisemeDoctor_Report")
    block.clear()
    block.write(text)
    print(text)
    return text


# ---------------------------------------------------------------- rename

def build_rename_plan(obj, mapping):
    """Split a mapping into (applicable [(old, new)], skipped [(old, new, why)]).

    Collision-safe: a rename is skipped when the source is absent, the
    target already exists (and is not itself renamed away in the same
    plan), or old == new. Basis is never renamed.
    """
    names = set(key_names(obj, include_basis=True))
    reference = obj.data.shape_keys.key_blocks[0].name if names else None
    plan, skipped = [], []
    renamed_away = {old for old, new in mapping.items()
                    if old in names and new != old}
    for old, new in mapping.items():
        if old == reference:
            skipped.append((old, new, "the reference key (Basis) is never renamed"))
        elif old not in names:
            skipped.append((old, new, "source key not present"))
        elif new == old:
            skipped.append((old, new, "already has the target name"))
        elif new in names and new not in renamed_away:
            skipped.append((old, new, "target name already exists"))
        else:
            plan.append((old, new))
    return plan, skipped


def apply_rename(obj, mapping):
    """Apply a rename mapping. Returns (renamed [(old, new)], skipped)."""
    plan, skipped = build_rename_plan(obj, mapping)
    blocks = obj.data.shape_keys.key_blocks
    for old, new in plan:
        blocks[old].name = new
    return plan, skipped


def load_mapping(path):
    """Load a user rename mapping from a JSON file ({old: new})."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("rename mapping must be a JSON object of old: new")
    return {str(k): str(v) for k, v in data.items()}


# ---------------------------------------------------------------- create

def _new_empty_key(obj, name):
    """Add a shape key that is guaranteed empty (identical to Basis).

    Blender's shape_key_add() initializes a new key from the *active*
    key's data, not from Basis, so the Basis positions are stamped in
    explicitly — a created key must deform nothing until sculpted.
    """
    kb = obj.shape_key_add(name=name, from_mix=False)
    basis = _key_positions(obj, obj.data.shape_keys.key_blocks[0])
    flat = np.empty(len(basis) * 3, dtype=np.float32)
    flat[:] = basis.reshape(-1).astype(np.float32)
    kb.data.foreach_set("co", flat)
    return kb


def create_missing(obj, include_blink=True):
    """Create missing viseme (and blink) keys as empty keys.

    New keys copy Basis, so they deform nothing until sculpted — this
    is a naming fix, not shape generation. Returns created names.
    """
    result = analyze(obj)
    created = []
    targets = list(result["visemes_missing"])
    if include_blink:
        targets += result["blink_missing"]
        # If one side of the blink pair exists, complete the pair even
        # when a single "blink" also got created above.
        names = set(key_names(obj)) | set(targets)
        if (BLINK_L in names) != (BLINK_R in names):
            targets.append(BLINK_R if BLINK_L in names else BLINK_L)
    for name in targets:
        if name not in key_names(obj):
            _new_empty_key(obj, name)
            created.append(name)
    return created


# ---------------------------------------------------------------- mirror

def mirror_key(obj, source_name, target_name, tolerance=None):
    """Copy a shape key across the X axis (.L <-> .R style).

    Correspondence is by mirrored vertex position (KD-tree nearest
    neighbour on the Basis shape). The deformation of each vertex is
    taken from its mirror partner with the X component negated.
    Vertices with no partner inside the tolerance keep no deformation
    and are counted in the returned quality report:

        {matched, unmatched, matched_pct, mean_residual,
         max_residual, tolerance}
    """
    blocks = obj.data.shape_keys.key_blocks
    if source_name not in blocks:
        raise KeyError("no shape key named %r" % source_name)
    basis_block = blocks[0]
    basis = _key_positions(obj, basis_block)
    source = _key_positions(obj, blocks[source_name])

    if tolerance is None:
        diag = float(np.linalg.norm(basis.max(axis=0) - basis.min(axis=0)))
        tolerance = max(diag * 0.005, 1e-6)

    mirrored = basis.copy()
    mirrored[:, 0] *= -1.0
    tree = kdtree.KDTree(len(basis))
    for i, co in enumerate(mirrored):
        tree.insert(co, i)
    tree.balance()

    deform = source - basis
    out = basis.copy()
    residuals = []
    matched = 0
    for i, co in enumerate(basis):
        _loc, partner, dist = tree.find(co)
        if dist <= tolerance:
            d = deform[partner].copy()
            d[0] *= -1.0
            out[i] = basis[i] + d
            residuals.append(float(dist))
            matched += 1

    if target_name in blocks:
        target = blocks[target_name]
    else:
        target = obj.shape_key_add(name=target_name, from_mix=False)
    flat = np.empty(len(basis) * 3, dtype=np.float32)
    flat[:] = out.reshape(-1).astype(np.float32)
    target.data.foreach_set("co", flat)

    n = len(basis)
    return {
        "source": source_name,
        "target": target_name,
        "vertices": n,
        "matched": matched,
        "unmatched": n - matched,
        "matched_pct": round(100.0 * matched / n, 2) if n else 0.0,
        "mean_residual": float(np.mean(residuals)) if residuals else None,
        "max_residual": float(np.max(residuals)) if residuals else None,
        "tolerance": tolerance,
    }
