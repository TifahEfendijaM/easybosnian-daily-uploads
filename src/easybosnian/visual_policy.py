"""Trusted per-image controls, applied before all normal Pillow safeguards."""
import copy
import secrets

from .designs import PANEL_STYLES, REVIEW_FADE_STYLES, REVIEW_EXAMPLE_FADE_STYLES, valid_panel_opacity


def panel_opacities(cards):
    """Answers are opaque; explanation opacity is sampled once in 0.1% steps."""
    return {card['kind']:100 if card['kind']=='quiz' else round(85+secrets.randbelow(151)/10,1)
            for card in cards}


def apply_policy(plan, *, panel_opacity):
    """Apply one sampled opacity to every bounded panel in this image.

    Validate every declared value before synchronization, so this cannot repair
    an invalid cosmetic field. Layout, copy, typography and colours stay intact.
    The reviewer-selected example preset is validated and preserved.
    """
    result=copy.deepcopy(plan)
    if not valid_panel_opacity(panel_opacity,legacy=False):
        raise ValueError('Assigned panel opacity outside the approved range')
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
    if plan['photo_window'] is None and plan.get('heading_tone') in ('ink_light','ink_paper','ink_accent','accent_light'):
        result['heading_fade']='defined'
    return result


def policy_metadata(plan, *, panel_opacity):
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    example_fade=example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None
    return safe_policy({'version':4,'panel_opacity':panel_opacity,'panel_opacity_applied':bool(panels),
                        'example_fade':example_fade,
                        'example_fade_applied':bool(example_fade is not None and example and
                                                     example['style']=='italic_photo_fade')},plan)


def safe_policy(value, plan):
    """Only fixed, checked policy metadata may reach the private run report."""
    fields={'panel_opacity','panel_opacity_applied','example_fade','example_fade_applied'}
    if (not isinstance(value,dict) or set(value) not in (fields,fields|{'version'})
            or ('version' in value and (type(value['version']) is not int or value['version'] not in (2,3,4)))
            or value['example_fade'] not in ((None,*REVIEW_EXAMPLE_FADE_STYLES) if value.get('version')==4 else (None,'sharp') if value.get('version')==3 else (None,*REVIEW_FADE_STYLES))
            or type(value['example_fade_applied']) is not bool
            or type(value['panel_opacity_applied']) is not bool):
        raise ValueError('Invalid safe rendering policy metadata')
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    opacity=value['panel_opacity']
    current=value.get('version') in (2,3,4)
    if (type(opacity) not in (int,float) or not valid_panel_opacity(opacity,legacy=not current) or (not current and opacity<70) or
            any(b.get('panel_opacity')!=opacity for b in panels)
            or value['panel_opacity_applied']!=bool(panels)
            or (current and any(b['role'] in ('A','B','C','D') for b in panels) and opacity!=100)):
        raise ValueError('Shared opacity differs from rendered composition')
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    active=bool(value['example_fade'] is not None and example and example['style']=='italic_photo_fade')
    if value.get('version')==4 and value['example_fade']!=(example.get('fade_style','standard') if example and example['style']=='italic_photo_fade' else None):
        raise ValueError('Selected shade differs from rendered composition')
    if active!=value['example_fade_applied'] or (active and example.get('fade_style')!=value['example_fade']):
        raise ValueError('Assigned shade differs from rendered composition')
    return dict(value)
