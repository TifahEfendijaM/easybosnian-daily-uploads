"""Active choices are distinct from archive-readable palette definitions."""
from .core import ROOT,read_json
RETIRED=frozenset(('graphite-chalk',))


def active():return {name:p for name,p in read_json(ROOT/'data/design-palettes.json').items() if name not in RETIRED}


def current(name):return 'mulberry-mint' if name=='graphite-chalk' else name


LIGHT_SURFACE_BACKING_GUIDANCE = (
    'For a LIGHT actual explanation-card MAIN SURFACE, compare the predefined same-family DARK '
    'light_example_backing, a suitable DARK version of a DIFFERENT hue already used in the chosen '
    "palette's accent or actual category surface, and a freely chosen harmonious different-hue DARK backing. "
    'Give these candidates equal consideration against the photograph and rendered composition. '
    'For the palette-related candidate, judge the actual accent/category hue relative to the actual body '
    'surface; a different role name alone does not make it a different hue. Choose a dark relative when '
    'the accent/category colour is bright, keeping readable white/warm-ivory example lettering. '
    'Palette membership alone does not establish harmony or give that candidate priority over a better fit. '
    'Prefer the predefined same-family backing when alternatives fit EQUALLY or ALMOST EQUALLY WELL. '
    'Choose a different hue when it gives a noticeable improvement in whole-image harmony, photographic '
    'connection or visual balance, even if modest; a barely distinguishable subjective advantage is not enough. '
    "The light_example_backing is curated for this palette's default light panel surface, NOT its ink or name. "
    'Check the ACTUAL selected main surface, including panel_tone and surface_richness. If a light accent '
    'surface has a different hue, do not mislabel the default-panel candidate as same-family: compare a '
    'suitable dark relative of that actual surface and other harmonious dark backings. '
    'Neither the predefined nor a different-hue choice is compulsory when it clashes or feels heavy; '
    'suitable dark neutrals remain available when clearly better. Apply this near-equal preference ONLY '
    'to light explanation surfaces; dark surfaces follow their separate different-hue-first rule. Never choose '
    'or lighten/darken the panel, change the overall palette or increase shade strength to simplify backing '
    'selection. Keep white/warm-ivory lettering, independent strength/edges/placement, and the existing '
    'rendered-card harmony and contrast checks. When selecting the predefined candidate, copy its exact '
    "hex into the example's backing_colour with a compatible explicit photo_tone; null does not select this role. "
    'This role is example-only selection metadata, never a body/title/category/badge/Story colour control '
    'or an automatic render/fallback substitution. No random draw or equal-frequency quota.'
)


DARK_SURFACE_BACKING_GUIDANCE = (
    'For a DARK actual explanation-card MAIN SURFACE only, try harmonious DIFFERENT-HUE DARK '
    'PRIMJER backings FIRST. Explicitly compare BOTH a suitable dark relative of a different hue '
    'already used in this palette’s accent or actual category surface AND a freely chosen '
    'different hue that harmonises with the photograph and composition. Neither of these two '
    'sources has automatic priority; choose the better fitting rendered result. Assess actual '
    'hues relative to the panel surface, not palette names or colour-role labels. Keep colours '
    'rich when fitting and lettering white/warm ivory. Only if neither different-hue approach '
    'produces a harmonious, readable, visually balanced result should you use a SAME-HUE dark '
    'backing. A suitable dark neutral can rescue the composition when these colours do not work. '
    'Never force a clash, excessive contrast or a heavy band just to obtain a different hue. '
    'Keep the already suitable palette, panel brightness and surface colour independent of this '
    'choice. Verify the actual blended result beside the panel in the phone-size finished-card '
    'review and revise a clear defect within the shared design budget. This preference applies '
    'ONLY to dark main surfaces; light surfaces retain their existing equal-consideration and '
    'same-family near-equal-fit preference.'
)
