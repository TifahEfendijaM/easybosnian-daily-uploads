"""Trusted per-image controls, applied before all normal Pillow safeguards."""
import copy
import secrets

from .designs import PANEL_STYLES, REVIEW_FADE_STYLES, valid_panel_opacity


def panel_opacities(cards):
    """Answers are opaque; explanation opacity is sampled once in 0.1% steps."""
    return {card['kind']:100 if card['kind']=='quiz' else round(85+secrets.randbelow(151)/10,1)
            for card in cards}


def example_fades(cards):
    """One independent fair draw per example, never redrawn after rejection."""
    return {card['kind']:secrets.choice(REVIEW_FADE_STYLES)
            for card in cards if card.get('example')}


def apply_policy(plan, *, panel_opacity, example_fade=None):
    """Apply one sampled opacity to every bounded panel in this image.

    Validate every declared value before synchronization, so this cannot repair
    an invalid cosmetic field. Layout, copy, typography and colours stay intact.
    The random example preset applies only to an existing photographic shade.
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
    if example_fade is not None:
        if example_fade not in REVIEW_FADE_STYLES:raise ValueError('Invalid assigned example shade')
        for block in result['blocks']:
            if block['role']=='example' and block['style']=='italic_photo_fade':
                if block.get('fade_style','standard') not in REVIEW_FADE_STYLES:
                    raise ValueError('Unsupported example shade')
                block['fade_style']=example_fade
    return result


def policy_metadata(plan, *, panel_opacity, example_fade=None):
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    return safe_policy({'version':2,'panel_opacity':panel_opacity,'panel_opacity_applied':bool(panels),
                        'example_fade':example_fade,
                        'example_fade_applied':bool(example_fade is not None and example and
                                                     example['style']=='italic_photo_fade')},plan)


def safe_policy(value, plan):
    """Only fixed, checked policy metadata may reach the private run report."""
    fields={'panel_opacity','panel_opacity_applied','example_fade','example_fade_applied'}
    if (not isinstance(value,dict) or set(value) not in (fields,fields|{'version'})
            or ('version' in value and (type(value['version']) is not int or value['version']!=2))
            or value['example_fade'] not in (None,*REVIEW_FADE_STYLES)
            or type(value['example_fade_applied']) is not bool
            or type(value['panel_opacity_applied']) is not bool):
        raise ValueError('Invalid safe rendering policy metadata')
    panels=[b for b in plan['blocks'] if b['style'] in PANEL_STYLES]
    opacity=value['panel_opacity']
    current=value.get('version')==2
    if (type(opacity) not in (int,float) or not valid_panel_opacity(opacity,legacy=not current) or (not current and opacity<70) or
            any(b.get('panel_opacity')!=opacity for b in panels)
            or value['panel_opacity_applied']!=bool(panels)
            or (current and any(b['role'] in ('A','B','C','D') for b in panels) and opacity!=100)):
        raise ValueError('Shared opacity differs from rendered composition')
    example=next((b for b in plan['blocks'] if b['role']=='example'),None)
    active=bool(value['example_fade'] is not None and example and example['style']=='italic_photo_fade')
    if active!=value['example_fade_applied'] or (active and example.get('fade_style')!=value['example_fade']):
        raise ValueError('Assigned shade differs from rendered composition')
    return dict(value)
