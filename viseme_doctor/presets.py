"""Built-in rename presets for Viseme Doctor.

A preset is a plain {old_name: new_name} dict. The rename engine in
core.py is collision-safe: a rename whose target already exists (and is
not itself being renamed away) is skipped and reported, never forced.

The Japanese preset covers the naming found on a large class of
Japanese game rips and MMD-style exports:

* Wink keys: ウインク family. ``ウィンク`` is the both-eyes blink,
  ``ウィンク右`` / ``ウィンク左`` are the right / left single-eye winks.
  Numbered variants (``ウィンク２`` etc.) are deliberately NOT in the
  preset: they are alternate takes of the same blink, mapping them
  would collide with the primary key, and the check report flags them
  as near-duplicates so the user can decide. Add them to a custom
  mapping if you really want them renamed.
* Kana mouth keys: the a-i-u-e-o kana are the standard five mouth
  shapes on Japanese rigs. They map to the closest VRChat visemes
  (あ→aa, い→ih, う→ou, え→e, お→oh). This is the mapping used by
  common VRC conversion guides; treat it as a naming fix, not a
  promise that the sculpted shape is a perfect phoneme match.
"""

# Both-eyes blink + single-eye winks.
JAPANESE_BLINK = {
    "ウィンク": "blink",
    "ウィンク右": "blink.R",
    "ウィンク左": "blink.L",
}

# Kana mouth shapes -> closest VRChat visemes.
JAPANESE_KANA_MOUTH = {
    "あ": "vrc.v_aa",
    "い": "vrc.v_ih",
    "う": "vrc.v_ou",
    "え": "vrc.v_e",
    "お": "vrc.v_oh",
}

PRESETS = {
    "japanese_vrc": {**JAPANESE_BLINK, **JAPANESE_KANA_MOUTH},
    "japanese_blink_only": dict(JAPANESE_BLINK),
    "japanese_kana_only": dict(JAPANESE_KANA_MOUTH),
}

PRESET_LABELS = {
    "japanese_vrc": "Japanese (blink + kana mouth)",
    "japanese_blink_only": "Japanese blink only",
    "japanese_kana_only": "Japanese kana mouth only",
}
