"""Active choices are distinct from archive-readable palette definitions."""
from .core import ROOT,read_json
RETIRED=frozenset(('graphite-chalk',))


def active():return {name:p for name,p in read_json(ROOT/'data/design-palettes.json').items() if name not in RETIRED}


def current(name):return 'mulberry-mint' if name=='graphite-chalk' else name


LIGHT_SURFACE_BACKING_GUIDANCE = (
    'For a LIGHT actual explanation-card MAIN SURFACE, compare the predefined same-family DARK '
    'light_example_backing and a freely chosen harmonious different-hue DARK backing EQUALLY before deciding. '
    'Prefer the predefined same-family backing when both fit EQUALLY or ALMOST EQUALLY WELL. '
    'Choose a different hue when it gives a noticeable improvement in whole-image harmony, photographic '
    'connection or visual balance, even if modest; a barely distinguishable subjective advantage is not enough. '
    "The light_example_backing is curated for this palette's default light panel surface, NOT its ink or name. "
    'Check the ACTUAL selected main surface, including panel_tone and surface_richness. If a light accent '
    'surface has a different hue, do not mislabel the default-panel candidate as same-family: compare a '
    'suitable dark relative of that actual surface and other harmonious dark backings. '
    'Neither the predefined nor a different-hue choice is compulsory when it clashes or feels heavy; '
    'suitable dark neutrals remain available when clearly better. Apply this near-equal preference ONLY '
    'to light explanation surfaces; DARK-surface harmony-first guidance stays unchanged. Never choose '
    'or lighten/darken the panel, change the overall palette or increase shade strength to simplify backing '
    'selection. Keep white/warm-ivory lettering, independent strength/edges/placement, and the existing '
    'rendered-card harmony and contrast checks. When selecting the predefined candidate, copy its exact '
    "hex into the example's backing_colour with a compatible explicit photo_tone; null does not select this role. "
    'This role is example-only selection metadata, never a body/title/category/badge/Story colour control '
    'or an automatic render/fallback substitution. No random draw or equal-frequency quota.'
)
