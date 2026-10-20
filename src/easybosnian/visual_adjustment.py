"""Bounded deterministic translation of approved model geometry, never a model retry.

Search nearby measured placements while preserving copy, styles, colours, fonts
and leading. Position repair preserves widths; a separate, reported PRIMJER-only
step may widen an artificial column to fit one line. Every candidate still goes
through full pixel rendering. This is not a global optimality claim.
"""
import copy
import math

from jsonschema import Draft202012Validator
from PIL import Image, ImageOps

GEOMETRY_ERRORS = frozenset((
    'Invalid hybrid composition contract',
    'Composition intersects the fixed heading, margin or logo strip',
    'Composition text blocks overlap or have no breathing room',
    'Photo window intersects heading or logo strip',
    'Separate photograph must remain free of explanation panels',
    'Visual quiz answers must follow the complete photograph',
    'Editorial explanation must precede the photograph',
    'Editorial italic footer must follow the photograph',
    'Italic example must fit directly inside the complete photograph',
    'Quiz choices must retain their visual reading order',
    'Bottom sheet requires a wide lower placement',
))
ADJUSTMENT_REASON='Nearest tested safe placement; design and typography preserved'
EXAMPLE_LINE_REASON='Single-line PRIMJER width and safe placement; design and typography preserved'


def adjustable_proposal(plan, model=False):
    """Permit only bounded integer-position mistakes, never untrusted fields/styles."""
    from .visual_placement import CARD_SCHEMA, MODEL_CARD_SCHEMA
    schema=copy.deepcopy(MODEL_CARD_SCHEMA if model else CARD_SCHEMA)
    for branch in schema['properties']['blocks']['items']['anyOf']:
        for key in ('x','y'):
            branch['properties'][key]={'type':'integer','minimum':-2700,'maximum':2700}
    schema['properties']['photo_window']['anyOf'][1]['properties']['y']={
        'type':'integer','minimum':-2700,'maximum':2700}
    if list(Draft202012Validator(schema).iter_errors(plan)):return None
    return copy.deepcopy(plan)


def safe_adjustment(value):
    if (not isinstance(value,dict) or set(value)!={'reason','moves'}
            or value['reason'] not in (ADJUSTMENT_REASON,EXAMPLE_LINE_REASON) or not isinstance(value['moves'],list)
            or not 1<=len(value['moves'])<=5):
        raise ValueError('Invalid safe placement adjustment metadata')
    seen=set()
    for move in value['moves']:
        if (not isinstance(move,dict) or set(move)!={'element','from','to'}
                or move['element'] not in ('body','example','A','B','C','D','photo_window')
                or move['element'] in seen):raise ValueError('Invalid safe placement adjustment metadata')
        seen.add(move['element'])
        expected={'y'} if move['element']=='photo_window' else {'x','y'}
        expanded=(move['element']=='example' and value['reason']==EXAMPLE_LINE_REASON
                  and isinstance(move.get('to'),dict) and 'width' in move['to'])
        if expanded:expected.add('width')
        for side in ('from','to'):
            pos=move[side]
            if (not isinstance(pos,dict) or set(pos)!=expected
                    or any(type(v) is not int or not -2700<=v<=2700 for v in pos.values())):
                raise ValueError('Invalid safe placement adjustment metadata')
        if move['from']==move['to']:raise ValueError('Invalid safe placement adjustment metadata')
        if expanded and not 300<=move['from']['width']<move['to']['width']<=952:
            raise ValueError('Invalid safe placement adjustment metadata')
    if value['reason']==EXAMPLE_LINE_REASON and not any('width' in m['to'] for m in value['moves']):
        raise ValueError('Invalid safe placement adjustment metadata')
    return copy.deepcopy(value)


def single_line_example_plan(card, proposal, background):
    """Prefer one exact-copy line when a wider horizontal slot safely permits it.

    Keep y, typography, style and every other block unchanged. Pixel contrast is
    checked by the caller's full render; if it fails, keep the original wrapping.
    """
    from .hybrid import block_spec, measured_plan, MIN_BLOCK_GAP, block_gap
    from .visual_placement import CARD_SCHEMA
    if list(Draft202012Validator(CARD_SCHEMA).iter_errors(proposal)):return None
    block=next((b for b in proposal['blocks'] if b['role']=='example'),None)
    if block is None:return None
    try:
        spec=block_spec(card,'example',block['width'],block['style'],block['font_size'],
                        block['line_spacing'],None,block.get('wrapping','balanced'))
    except ValueError:return None
    if len(spec['rows'])<=1:return None
    face=spec['face'];text=card['example'];box=face.getbbox(text)
    width=math.ceil(max(face.getlength(text),box[2]-box[0]))
    if not block['width']<width<=952:return None
    left,right=64,880 if block['style']=='italic_footer' else 1016
    window=proposal['photo_window']
    if window is not None and proposal['design']=='hybrid':
        with Image.open(background) as photo:
            photo_width=ImageOps.contain(photo,(952,window['height']),Image.Resampling.LANCZOS).width
        left=max(left,math.ceil((1080-photo_width)/2+20))
        right=min(right,math.floor((1080+photo_width)/2-20))
    high=min(716,right-width)
    if high<left:return None
    anchors={max(left,min(high,block['x'])),left,high}
    # Nearby horizontal slots preserve the chosen vertical placement. The full
    # measured plan rejects collisions, protected photo regions and bad bounds.
    for other in proposal['blocks']:
        if other['role']=='example':continue
        gap=block_gap('example',other['role'])
        anchors.update((other['x']+other['width']+gap,other['x']-width-gap))
    for x in sorted((x for x in anchors if left<=x<=high),key=lambda x:(abs(x-block['x']),x)):
        candidate=copy.deepcopy(proposal)
        target=next(b for b in candidate['blocks'] if b['role']=='example')
        target.update(x=x,width=width)
        try:
            measured=measured_plan(card,candidate)
        except ValueError:continue
        if len(next(b for b in measured if b['role']=='example')['rows'])==1:return candidate
    return None


def applied_adjustment(requested, applied):
    """Describe only actual, approved positional/single-line width changes."""
    moves=[]
    a,b=requested['photo_window'],applied['photo_window']
    if a is not None and b is not None and a['y']!=b['y']:
        moves.append({'element':'photo_window','from':{'y':a['y']},'to':{'y':b['y']}})
    wider=False
    for old,new in zip(requested['blocks'],applied['blocks']):
        keys=('x','y','width') if old['width']!=new['width'] else ('x','y')
        if any(old[k]!=new[k] for k in keys):
            wider=wider or 'width' in keys
            moves.append({'element':old['role'],'from':{k:old[k] for k in keys},'to':{k:new[k] for k in keys}})
    if not moves:return None
    return safe_adjustment({'reason':EXAMPLE_LINE_REASON if wider else ADJUSTMENT_REASON,'moves':moves})


def nearest_valid_plan(card, proposal, background):
    from .hybrid import heading, block_spec, occupied_width, measured_plan, MIN_BLOCK_GAP, block_gap, roles
    original=adjustable_proposal(proposal)
    if original is None or original['confidence']!='high':return None
    try:
        measured_plan(card,original)
        return None  # Valid intent must never be moved just for aesthetics.
    except ValueError as error:
        if str(error) not in GEOMETRY_ERRORS:return None
    if [b['role'] for b in original['blocks']]!=roles(card):return None
    result=copy.deepcopy(original);header=heading(card)[2];window=result['photo_window']
    if window:
        low=max(250,math.ceil(header+24));high=min(770,1170-window['height'])
        if low>high:return None
        window['y']=max(low,min(high,window['y']))
    specs=[]
    try:
        for block in result['blocks']:
            spec=block_spec(card,block['role'],block['width'],block['style'],block['font_size'],
                            block['line_spacing'],block.get('max_lines'),block.get('wrapping','balanced'))
            specs.append(spec)
    except ValueError:return None
    photo_bounds=None
    if window and result['design']=='hybrid':
        with Image.open(background) as photo:
            width,height=ImageOps.contain(photo,(952,window['height']),Image.Resampling.LANCZOS).size
        photo_bounds=((1080-width)//2,window['y'],(1080+width)//2,window['y']+height)
    bounds=[];targets=[]
    for block,spec in zip(result['blocks'],specs):
        footer=block['style']=='italic_footer'
        xlo=64;xhi=min(716,(880 if footer else 1016)-block['width'])
        ylo=max(200,math.ceil(header+24));yhi=min(1240,math.floor((1286 if footer else 1170)-spec['height']))
        if block['style']=='bottom_sheet':ylo=max(ylo,700)
        intervals=[(ylo,yhi)]
        if window:
            if result['design']=='editorial':
                if block['role']=='body':intervals=[(ylo,min(yhi,math.floor(window['y']-24-spec['height'])))]
                else:intervals=[(max(ylo,window['y']+window['height']+24),yhi)]
            elif block['role']=='example':
                xlo=max(xlo,photo_bounds[0]+20);xhi=min(xhi,photo_bounds[2]-20-block['width'])
                intervals=[(max(ylo,photo_bounds[1]+20),min(yhi,math.floor(photo_bounds[3]-20-spec['height'])))]
            elif card.get('quiz_format')=='visual_identification':
                intervals=[(max(ylo,window['y']+window['height']+24),yhi)]
            else:
                intervals=[(ylo,min(yhi,math.floor(window['y']-24-spec['height']))),
                           (max(ylo,window['y']+window['height']+24),yhi)]
        intervals=[(math.ceil(a),math.floor(b)) for a,b in intervals if a<=b]
        if xlo>xhi or not intervals:return None
        visible=occupied_width(spec);ow=min(block['width'],visible) if visible is not None else block['width']
        bounds.append((xlo,xhi,intervals,ow,spec['height']))
        targets.append((block['x'],block['y'],ow,spec['height']))
    # Beam states are distance, placed coordinates and their occupied rectangles.
    beam=[(0,[],[])]
    for index,(block,limits) in enumerate(zip(result['blocks'],bounds)):
        xlo,xhi,intervals,ow,height=limits;expanded=[]
        for cost,positions,boxes in beam:
            anchors=[(*target,result['blocks'][j]['role']) for j,target in enumerate(targets)]
            anchors.extend((a,b,c-a,d-b,result['blocks'][j]['role']) for j,(a,b,c,d) in enumerate(boxes))
            xs={max(xlo,min(xhi,block['x'])),xlo,xhi}
            ys={max(a,min(b,block['y'])) for a,b in intervals}
            for a,b in intervals:ys.update((a,b))
            for x,y,w,h,other_role in anchors:
                gap=block_gap(block['role'],other_role)
                xs.update((round(x+w+gap),round(x-ow-gap)))
                ys.update((math.ceil(y+h+gap),math.floor(y-height-gap)))
            candidates=[]
            for x in sorted(xs):
                if not xlo<=x<=xhi:continue
                for y in sorted(ys):
                    if not any(a<=y<=b for a,b in intervals):continue
                    if card['kind']=='quiz' and positions and (y,x)<(positions[-1][1],positions[-1][0]):continue
                    box=(x,y,x+ow,y+height)
                    if any(box[0]<a2+block_gap(block['role'],result['blocks'][j]['role']) and box[2]>a0-block_gap(block['role'],result['blocks'][j]['role'])
                           and box[1]<a3+block_gap(block['role'],result['blocks'][j]['role']) and box[3]>a1-block_gap(block['role'],result['blocks'][j]['role'])
                           for j,(a0,a1,a2,a3) in enumerate(boxes)):continue
                    distance=(x-block['x'])**2+(y-block['y'])**2
                    candidates.append((cost+distance,positions+[(x,y)],boxes+[box]))
            expanded.extend(sorted(candidates,key=lambda s:(s[0],s[1]))[:24])
        if not expanded:return None
        beam=sorted(expanded,key=lambda s:(s[0],s[1]))[:96]
    for _,positions,_ in beam:
        candidate=copy.deepcopy(result)
        for block,(x,y) in zip(candidate['blocks'],positions):block.update(x=x,y=y)
        try:measured_plan(card,candidate)
        except ValueError:continue
        moves=[]
        if window and window['y']!=original['photo_window']['y']:
            moves.append({'element':'photo_window','from':{'y':original['photo_window']['y']},'to':{'y':window['y']}})
        for old,new in zip(original['blocks'],candidate['blocks']):
            if (old['x'],old['y'])!=(new['x'],new['y']):
                moves.append({'element':old['role'],'from':{k:old[k] for k in ('x','y')},'to':{k:new[k] for k in ('x','y')}})
        if moves:return candidate,safe_adjustment({'reason':ADJUSTMENT_REASON,'moves':moves})
    return None
