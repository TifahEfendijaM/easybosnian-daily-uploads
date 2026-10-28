"""Trusted per-image controls, applied before all normal Pillow safeguards."""
import copy

from .designs import PANEL_STYLES, REVIEW_EXAMPLE_FADE_STYLES, valid_panel_opacity


def panel_opacities(cards):
    """Fresh bounded panels always use 100%; no model or random opacity choice."""
    return {card['kind']:100 for card in cards}


def selected_panel_opacity(plan):
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    values=[b.get('panel_opacity',100) for b in panels]
    if any(not valid_panel_opacity(v,legacy=False) for v in values):
        raise ValueError('Panel opacity outside the approved range')
    if values and any(v!=values[0] for v in values):
        raise ValueError('All panels in an image must share one opacity')
    return values[0] if values else 100


def apply_policy(plan, *, panel_opacity=None):
    """Enforce fully opaque fresh panels; archive rendering bypasses this policy."""
    result=copy.deepcopy(plan)
    panels=[b for b in result['blocks'] if b['style'] in PANEL_STYLES]
    if any(not valid_panel_opacity(b.get('panel_opacity',100),legacy=False) for b in panels):
        raise ValueError('Panel opacity outside the approved range')
    if panel_opacity is not None:
        if not valid_panel_opacity(panel_opacity,legacy=False):
            raise ValueError('Assigned panel opacity outside the approved range')
        for block in panels:block['panel_opacity']=panel_opacity
    selected_panel_opacity(result)
    for block in result['blocks']:
        if (block['role']=='example' and block['style']=='italic_photo_fade'
                and block.get('fade_style','standard') not in REVIEW_EXAMPLE_FADE_STYLES):
            raise ValueError('Unsupported example shade')
    return result


def policy_metadata(plan, *, panel_opacity=None):
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    actual=selected_panel_opacity(plan)
    if panel_opacity is not None and panel_opacity!=actual:
        raise ValueError('Shared opacity differs from rendered composition')
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    example_fade=example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None
    return safe_policy({'version':9,'panel_opacity':actual,'panel_opacity_applied':bool(panels),
                        'example_fade':example_fade,
                        'example_fade_applied':bool(example_fade is not None and example and
                                                     example['style']=='italic_photo_fade')},plan)


def safe_policy(value, plan):
    """Only checked policy metadata may reach reports; old policies stay exact."""
    fields={'panel_opacity','panel_opacity_applied','example_fade','example_fade_applied'}
    if (not isinstance(value,dict) or set(value) not in (fields,fields|{'version'})
            or ('version' in value and (type(value['version']) is not int or value['version'] not in (2,3,4,5,6,7,8,9)))
            or value['example_fade'] not in ((None,*REVIEW_EXAMPLE_FADE_STYLES) if value.get('version') in (4,5,6,7,8,9) else (None,'sharp') if value.get('version')==3 else (None,'standard','defined'))
            or type(value['example_fade_applied']) is not bool
            or type(value['panel_opacity_applied']) is not bool):
        raise ValueError('Invalid safe rendering policy metadata')
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    opacity=value['panel_opacity'];version=value.get('version')
    minimum=100 if version in (8,9) else 90 if version==7 else 85 if version in (2,3,4,5,6) else 70
    if (type(opacity) not in (int,float) or not valid_panel_opacity(opacity) or opacity<minimum or
            any(b.get('panel_opacity')!=opacity for b in panels)
            or value['panel_opacity_applied']!=bool(panels)
            or (version in (6,8,9) and opacity!=100)
            or (version in (2,3,4,5,6) and any(b['role'] in ('A','B','C','D') for b in panels) and opacity!=100)):
        raise ValueError('Shared opacity differs from rendered composition')
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    active=bool(value['example_fade'] is not None and example and example['style']=='italic_photo_fade')
    if version in (4,5,6,7,8,9) and value['example_fade']!=(example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None):
        raise ValueError('Selected shade differs from rendered composition')
    if active!=value['example_fade_applied'] or (active and example.get('fade_style')!=value['example_fade']):
        raise ValueError('Assigned shade differs from rendered composition')
    return dict(value)
