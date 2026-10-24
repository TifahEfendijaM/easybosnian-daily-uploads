"""Trusted per-image controls, applied before all normal Pillow safeguards."""
import copy

from .designs import PANEL_STYLES, REVIEW_EXAMPLE_FADE_STYLES, valid_panel_opacity


def panel_opacities(cards):
    """Keep approved panel colours intact instead of tinting them with the photo."""
    return {card['kind']:100 for card in cards}


def apply_policy(plan, *, panel_opacity):
    """Apply the fixed opaque surface to every bounded panel in this image.

    Validate every declared value before synchronization, so this cannot repair
    an invalid cosmetic field. Layout, copy, typography and colours stay intact.
    The reviewer-selected example preset is validated and preserved.
    """
    result=copy.deepcopy(plan)
    if type(panel_opacity) not in (int,float) or panel_opacity!=100:
        raise ValueError('Assigned panel opacity must be 100 percent; fully opaque surfaces are required')
    panels=[b for b in result['blocks'] if b['style'] in PANEL_STYLES]
    if any(not valid_panel_opacity(b.get('panel_opacity',100),legacy=False) for b in panels):
        raise ValueError('Panel opacity outside the approved range')
    if panels:
        if any(b['role'] in ('A','B','C','D') for b in panels) and panel_opacity!=100:
            raise ValueError('Answer panels require fully opaque surfaces')
        for block in panels:block['panel_opacity']=panel_opacity
    for block in result['blocks']:
        if (block['role']=='example' and block['style']=='italic_photo_fade'
                and block.get('fade_style','standard') not in REVIEW_EXAMPLE_FADE_STYLES):
            raise ValueError('Unsupported example shade')
    return result


def policy_metadata(plan, *, panel_opacity):
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    example_fade=example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None
    return safe_policy({'version':6,'panel_opacity':panel_opacity,'panel_opacity_applied':bool(panels),
                        'example_fade':example_fade,
                        'example_fade_applied':bool(example_fade is not None and example and
                                                     example['style']=='italic_photo_fade')},plan)


def safe_policy(value, plan):
    """Only fixed, checked policy metadata may reach the private run report."""
    fields={'panel_opacity','panel_opacity_applied','example_fade','example_fade_applied'}
    if (not isinstance(value,dict) or set(value) not in (fields,fields|{'version'})
            or ('version' in value and (type(value['version']) is not int or value['version'] not in (2,3,4,5,6)))
            or value['example_fade'] not in ((None,*REVIEW_EXAMPLE_FADE_STYLES) if value.get('version') in (4,5,6) else (None,'sharp') if value.get('version')==3 else (None,'standard','defined'))
            or type(value['example_fade_applied']) is not bool
            or type(value['panel_opacity_applied']) is not bool):
        raise ValueError('Invalid safe rendering policy metadata')
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    opacity=value['panel_opacity']
    current=value.get('version') in (2,3,4,5,6)
    if (type(opacity) not in (int,float) or not valid_panel_opacity(opacity,legacy=not current) or (not current and opacity<70) or
            any(b.get('panel_opacity')!=opacity for b in panels)
            or value['panel_opacity_applied']!=bool(panels)
            or (value.get('version')==6 and opacity!=100)
            or (current and any(b['role'] in ('A','B','C','D') for b in panels) and opacity!=100)):
        raise ValueError('Shared opacity differs from rendered composition')
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    active=bool(value['example_fade'] is not None and example and example['style']=='italic_photo_fade')
    if value.get('version') in (4,5,6) and value['example_fade']!=(example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None):
        raise ValueError('Selected shade differs from rendered composition')
    if active!=value['example_fade_applied'] or (active and example.get('fade_style')!=value['example_fade']):
        raise ValueError('Assigned shade differs from rendered composition')
    return dict(value)
