"""Compact exact-copy fit data; measurements, never style recommendations."""
import copy
import json
from functools import lru_cache

from .designs import BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES, FONT_RANGES, role_type
from .hybrid import block_spec
from .render import density

PROFILE_COLUMNS = ['width', 'font_size', 'line_spacing', 'line_count', 'height']


def block_measurements(card, role):
    """Deduplicate equivalent metrics without aliasing their actual renderers.

    All renderer choices and intermediate widths/sizes remain available. These
    samples let the reviewer choose exact known fits instead of guessing that
    wrapping scales linearly when typography changes.
    """
    source={key:card[key] for key in ('kind','question','body','example') if key in card}
    if card['kind']=='quiz':source['options']=[{'label':o['label'],'text':o['text']} for o in card['options']]
    return copy.deepcopy(_measurements(json.dumps(source,ensure_ascii=False,sort_keys=True),role))


@lru_cache(maxsize=64)
def _measurements(source, role):
    # Process-local exact-copy cache only; no private output or history writes.
    card=json.loads(source)
    styles = EXAMPLE_STYLES if role=='example' else BODY_STYLES if role=='body' else ANSWER_STYLES
    low,high = FONT_RANGES[role_type(role)]
    sizes = sorted({*range(low,high+1,4),high,min(density(card)[0],high)})
    profiles={};by_style={}
    for style in styles:
        # Shared measurement only: all style IDs still draw distinct pixels.
        family=('rounded' if style in ANSWER_STYLES and style not in ('split_panel','pill')
                else 'italic_photo' if style=='italic_photo_fade' else style)
        if family not in profiles:
            rows=[]
            for width in (300,480,660,800,952):
                for size in sizes:
                    for leading in (1.30,1.35,1.40,1.45,1.50,1.55):
                        try:spec=block_spec(card,role,width,family,size,leading)
                        except ValueError as error:
                            if str(error)=='Requested leading collides with measured glyphs':continue
                            break
                        rows.append([width,size,leading,len(spec['rows']),spec['height']])
                        break
            profiles[family]=rows
        by_style[style]={'measurement_family':family}
    return {'measurements_by_style':by_style,'fit_profiles':profiles}
