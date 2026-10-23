"""Replace the smallest failing element set; preserved elements never move."""
import copy
import itertools
import math
from jsonschema import Draft202012Validator
from PIL import Image, ImageOps
from .hybrid import default_plan, editorial_plan, roles
from .visual_adjustment import nearest_valid_plan

GLOBAL_GROUPS={'category':('category_style','category_tone'),
               'heading':('heading_tone','heading_fade'), 'photo_window':('photo_window',)}
RECOVERY_REASON='Failed elements replaced; other approved elements preserved unchanged'


def safe_recovery(value):
    names={'body','example','A','B','C','D',*GLOBAL_GROUPS}
    if (not isinstance(value,dict) or set(value)!={'reason','preserved','fallback'}
            or value['reason']!=RECOVERY_REASON
            or any(not isinstance(value[k],list) or not value[k] for k in ('preserved','fallback'))
            or any(not isinstance(n,str) or n not in names for k in ('preserved','fallback') for n in value[k])
            or len(set(value['preserved']+value['fallback']))!=len(value['preserved']+value['fallback'])):
        raise ValueError('Invalid element recovery metadata')
    return copy.deepcopy(value)


def recoverable_proposal(card, requested):
    from .visual_placement import CARD_SCHEMA
    if not isinstance(requested,dict) or requested.get('confidence')!='high':return False
    expected=roles(card);blocks=requested.get('blocks')
    if (not isinstance(blocks,list) or len(blocks)>len(expected)
            or any(not isinstance(b,dict) for b in blocks)
            or len({b.get('role') for b in blocks if isinstance(b.get('role'),str)})!=len(blocks)
            or any(b.get('role') not in expected for b in blocks)
            or [b['role'] for b in blocks]!=[r for r in expected if r in {b['role'] for b in blocks}]):return False
    try:baseline=editorial_plan(card) if requested.get('design')=='editorial' else default_plan(card)
    except ValueError:return False
    root=copy.deepcopy(requested);root['blocks']=baseline['blocks']
    for keys in GLOBAL_GROUPS.values():
        for key in keys:
            if key in baseline:root[key]=copy.deepcopy(baseline[key])
    return not list(Draft202012Validator(CARD_SCHEMA).iter_errors(root))


def replacement(card,old,base,window,design,background,faithful):
    from .visual_placement import BLOCK_SCHEMA
    block=copy.deepcopy(base)
    if faithful:
        schema=next(s for s in BLOCK_SCHEMA['anyOf'] if old['role'] in s['properties']['role']['enum'])
        for key,value in old.items():
            if key in schema['properties'] and not list(Draft202012Validator(schema['properties'][key]).iter_errors(value)):
                block[key]=copy.deepcopy(value)
        # A line cap must never truncate the exact copy during local recovery.
        block['max_lines']=None
        if block['role']=='example':block['style']='italic_footer' if design=='editorial' else ('italic_photo' if old.get('style')=='italic_photo' else 'italic_photo_fade')
        elif design=='editorial':block.update(style='plain',panel_tone='auto',panel_opacity=100)
    # The requested position remains the search target even when other fields fail.
    for key in ('x','y'):
        if type(old.get(key)) is int and -2700<=old[key]<=2700:
            block[key]=max(64 if key=='x' else 200,min(716 if key=='x' else 1240,old[key]))
    if block['role']=='example' and window and design=='hybrid':
        with Image.open(background) as photo:
            width,_=ImageOps.contain(photo,(952,window['height']),Image.Resampling.LANCZOS).size
        block['width']=min(block['width'],width-40)
        left=math.ceil((1080-width)/2)+20;right=math.floor((1080+width)/2)-20
        block['x']=max(left,min(block['x'],right-block['width']))
    return block


def recover_elements(card, requested, background, render, *, required=()):
    """Search smallest subsets; full glyph/pixel validation remains mandatory.

    Every untouched block/group is exact. Failed blocks first retain their safe
    style/typography/colour intent and nearest tested position; trusted defaults
    are used only for attributes that cannot survive the full checks.
    """
    from .visual_placement import CARD_SCHEMA
    if not recoverable_proposal(card,requested):return None
    expected=roles(card)
    requested=copy.deepcopy(requested)
    blocks={b['role']:b for b in requested['blocks']}
    required=set(required)|{r for r in expected if r not in blocks}
    requested['blocks']=[blocks.get(r,{'role':r}) for r in expected]
    baseline=editorial_plan(card) if requested['design']=='editorial' else default_plan(card)
    groups=[*expected,*GLOBAL_GROUPS]
    for size in range(1,len(groups)):
        for failed in itertools.combinations(groups,size):
            if not required<=set(failed):continue
            for faithful in (True,False):
                candidate=copy.deepcopy(requested)
                for name in failed:
                    if name in GLOBAL_GROUPS:
                        for key in GLOBAL_GROUPS[name]:candidate[key]=copy.deepcopy(baseline[key])
                window=candidate.get('photo_window')
                if list(Draft202012Validator(CARD_SCHEMA['properties']['photo_window']).iter_errors(window)):continue
                for index,role in enumerate(expected):
                    if role in failed:candidate['blocks'][index]=replacement(card,requested['blocks'][index],baseline['blocks'][index],window,candidate['design'],background,faithful)
                if list(Draft202012Validator(CARD_SCHEMA).iter_errors(candidate)):continue
                locked=tuple(r for r in expected if r not in failed)
                try:metrics=render(candidate)
                except ValueError as error:
                    adjusted=nearest_valid_plan(card,candidate,background,locked_roles=locked,
                                               lock_window='photo_window' not in failed,reason=str(error))
                    if adjusted is None:continue
                    try:metrics=render(adjusted[0])
                    except ValueError:continue
                applied=metrics['composition']
                if any(applied['blocks'][i]!=requested['blocks'][i] for i,r in enumerate(expected) if r not in failed):continue
                if any(any(applied.get(k)!=requested.get(k) for k in keys)
                       for name,keys in GLOBAL_GROUPS.items() if name not in failed):continue
                detail=safe_recovery({'reason':RECOVERY_REASON,'preserved':[n for n in groups if n not in failed],'fallback':list(failed)})
                return metrics,detail
    return None
