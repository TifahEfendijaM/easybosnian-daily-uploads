"""Measured photographic compositions from data, never model-generated drawing code."""
import json
import copy
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageChops

from .core import ROOT
from .designs import (BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES, PANEL_STYLES,
                      MARKER_STYLES, CATEGORY_STYLES, PHOTO_TONES,
                      FADE_STYLES, panel_alpha, panel_colours, typography)
from .render import (HEIGHT, WIDTH, LABELS, centered, contrast, density,
                     draw_rows, font, measure, wrap)

MIN_BLOCK_GAP = 8
CATEGORY_TOP = 64
CATEGORY_HEIGHT = 62
HEADING_TOP = 174
EXAMPLE_BLOCK_GAP = 32
EXAMPLE_FADE_PADDING = 18
SHARP_EXAMPLE_TOP_PADDING = 12
# Renderer-owned vertical feathers beyond each measured text band.
# Keep PRIMJER compact while restoring the title's earlier, broader gradient.
PHOTO_FADE_FEATHER = 48
# Qualitative PRIMJER intent maps to trusted alpha, never arbitrary opacity.
EXAMPLE_SHADE_MINIMUMS = {'soft':64, 'medium':128, 'strong':192}
EXAMPLE_SHADE_LEVELS = (64,90,128,130,170,192,210,240)
# Restore the earlier title fade extent without widening PRIMJER shading.
TITLE_FADE_FEATHER = 100
TITLE_FADE_PADDING = 24  # Equal upper/lower shoulders; category elements draw above the title fade.
# Start with faint title backings; stronger candidates require measured need.
TITLE_SHADE_LEVELS = (12, 24, 36, 48, 54, 66, 78, 90, 102, 114, 126, 130, 144, 170, 210, 240)
NONQUIZ_TITLE_MAX_SHADE = 126  # Recorded Hoćemo li unutra? reference, 25 October.
NEAR_EXAMPLE_TITLE_MAX_SHADE = 78
TITLE_EXAMPLE_NEAR_GAP = 100
# Finer steps avoid unnecessarily whitening a photograph when a weaker white
# title backing already passes contrast. Black backings keep their existing preset.
TITLE_WHITE_SHADE_LEVELS = tuple(sorted(set(TITLE_SHADE_LEVELS) | set(range(2,145,2)) | {156,190,225}))
# Approved stronger quiz intent starts at this trusted alpha, never a model number.
QUIZ_TITLE_MIN_SHADE = 90
TITLE_FADE_POWER = 2.5
# Title shading spans the entire image at equal opacity on each horizontal row.
# Keep the faint contrast-driven strength and smooth vertical tapers.
TITLE_SURROUND_OPACITY = 1
TITLE_WHITE_SURROUND_OPACITY = 1
TITLE_SURROUND_FEATHER = 180


def serif(size, italic=False):
    face = ImageFont.truetype(str(ROOT/'assets/fonts'/('Lora-Italic.ttf' if italic else 'Lora.ttf')), size)
    face.set_variation_by_axes([400 if italic else 600])
    return face


def heading(card):
    face = serif(50 if card['kind']=='quiz' else 74)
    rows = wrap(card.get('question') if card['kind']=='quiz' else card['heading'], face, 952)
    if len(rows) > (3 if card['kind']=='quiz' else 2):
        raise ValueError('Hybrid heading exceeds measured lines; never truncate')
    return face, rows, HEADING_TOP + measure(rows, face)[0]


def title_example_proximity(blocks, header_end):
    """Use the existing title-boundary-to-example-start distance unchanged."""
    example=next((b for b in blocks if b.get('role')=='example'),None)
    if example is None:return 'absent'
    return 'near' if example['y']-header_end<TITLE_EXAMPLE_NEAR_GAP else 'far'


def roles(card):
    return ([o['label'] for o in card['options']] if card['kind']=='quiz' else
            ['body'] + (['example'] if card.get('example') else []))


def block_spec(card, role, width, style=None, font_size=None, line_spacing=1.30,
               max_lines=None, wrapping='balanced'):
    """Trusted fonts/presets; actual glyphs and shared answer cells determine height."""
    style=style or ('italic_photo_fade' if role=='example' else 'rounded')
    size,padding=density(card)
    size=font_size if font_size is not None else (min(size,36) if role=='example' else size)
    typography(role,size,line_spacing,max_lines,wrapping)
    if role=='example':
        if style not in EXAMPLE_STYLES:raise ValueError('Unsupported example style')
        face=serif(size,italic=True);text=card['example'];text_width=width
        extra=measure(['PRIMJER'],font(21,'SemiBold'))[0]+16+(24 if style=='italic_footer' else 0)
        inset=0
    else:
        if style not in (BODY_STYLES if role=='body' else ANSWER_STYLES):
            raise ValueError('Unsupported explanation/answer style')
        face=font(size,'Regular')
        text=card['body'] if role=='body' else next(o['text'] for o in card['options'] if o['label']==role)
        inset=(0 if style=='plain' else
               (106 if style=='split_panel' else padding if role=='body' and style=='rounded_plain'
                else padding+24 if role=='body' else 94))
        text_width=width-inset-(0 if style=='plain' else padding)
        extra=0 if style=='plain' else 2*padding
    rows=wrap(text,face,text_width,wrapping)
    if any(face.getbbox(row)[2]-face.getbbox(row)[0]>text_width for row in rows):
        raise ValueError('Actual glyphs exceed block width')
    if max_lines is not None and len(rows)>max_lines:raise ValueError('Exact text exceeds maximum lines; never truncate')
    if style=='pill' and len(rows)>2:raise ValueError('Pill answers are limited to two measured lines')
    if style=='folded_corner' and len(rows)>2:raise ValueError('Folded answers are limited to two measured lines')
    text_height,step=measure(rows,face,line_spacing)
    text_offset=0
    if role not in ('body','example'):
        # A shared font cell keeps neighbouring answers' panel heights and
        # baselines aligned despite different accents or descenders. Include
        # all exact choices so unusual Unicode glyphs remain inside the cell.
        samples=['ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzČĆŠŽĐčćšžđ0123456789',
                 *(option['text'] for option in card['options'])]
        bounds=[face.getbbox(text) for text in samples]
        cell_top=min(box[1] for box in bounds)
        text_offset=min(face.getbbox(row)[1] for row in rows)-cell_top
        text_height=max(box[3] for box in bounds)-cell_top+(len(rows)-1)*step
    height=text_height+extra
    if role not in ('body','example'):height=max(92,height)
    return {'face':face,'rows':rows,'height':height,'padding':padding,'size':size,'style':style,
            'font_size':size,'line_spacing':line_spacing,'max_lines':max_lines,'wrapping':wrapping,'text_inset':inset,
            'text_cell_height':text_height,'text_cell_offset':text_offset}


def fallback_spec(card,role,width=952,style=None):
    """Measured safe leading for renderer-owned defaults; never repair model intent."""
    for leading in (1.30,1.35,1.40,1.45,1.50,1.55):
        try:return block_spec(card,role,width,style,line_spacing=leading)
        except ValueError as error:
            if str(error)!='Requested leading collides with measured glyphs':raise
    raise ValueError('No approved fallback leading fits measured glyphs')


def declared_block(card,role,width=952,style=None,**geometry):
    spec=fallback_spec(card,role,width,style)
    return {'role':role,'style':spec['style'],'width':width,'font_size':spec['size'],
            **({'panel_opacity':100} if role!='example' else {}),
            **({'panel_tone':'auto'} if role!='example' else {}),
            **({'marker_style':'circle'} if role not in ('body','example') else {}),
            **({'photo_tone':'auto','fade_style':'standard','shade_strength':'soft'} if role=='example' else {}),
            'line_spacing':spec['line_spacing'],'max_lines':None,'wrapping':'balanced',**geometry}


def default_plan(card):
    """Deterministic measured fallback, never another model/image call."""
    y=heading(card)[2]+28;blocks=[];window=None
    if card.get('quiz_format')=='visual_identification':
        y=max(250,y)
        specs=[fallback_spec(card,role,952) for role in roles(card)]
        height=min(510,1170-y-28-sum(s['height'] for s in specs)-16*(len(specs)-1))
        if height<240:raise ValueError('Visual quiz cannot preserve complete photo and exact copy')
        window={'y':y,'height':height,'fit':'contain'};y+=height+28
    for role in roles(card):
        spec=fallback_spec(card,role,952)
        if role=='example':
            # Bottom-biased, measured and logo-safe; never model repair or truncation.
            y=max(y,1126-spec['height'])
        blocks.append(declared_block(card,role,x=64,y=round(y)))
        y+=spec['height']+(40 if role=='body' else 16)
    return {'confidence':'uncertain','design':'hybrid','category_style':'rounded','category_tone':'auto',
            'heading_tone':'auto','heading_fade':'standard','heading_shade':'gentle','palette_exception':'none','photo_window':window,'blocks':blocks}


def editorial_plan(card):
    if card['kind']=='quiz':raise ValueError('Quiz retains its clear photographic design')
    top=heading(card)[2]+28
    body=declared_block(card,'body',style='plain',x=64,y=top)
    photo_top=top+fallback_spec(card,'body',952,'plain')['height']+24
    footer_height=fallback_spec(card,'example',800,'italic_footer')['height'] if card.get('example') else 0
    photo_height=min(560,1170-photo_top,1286-photo_top-footer_height-24)
    if photo_height<400:raise ValueError('Editorial reference cannot fit exact copy')
    blocks=[body]
    if card.get('example'):
        blocks.append(declared_block(card,'example',800,'italic_footer',x=64,y=photo_top+photo_height+24))
    return {'confidence':'high','design':'editorial','category_style':'underlined','category_tone':'auto',
            'heading_tone':'auto','heading_fade':'standard','heading_shade':'gentle','palette_exception':'none',
            'photo_window':{'y':photo_top,'height':photo_height,'fit':'cover'},'blocks':blocks}


def occupied_width(spec):
    """Visible unboxed copy/rules, rather than unused wrapping width.

    Opaque/translucent panels and footer rules occupy their full declared
    width. Fades remain renderer-owned and receive final-pixel contrast checks.
    """
    style=spec['style']
    if style in PANEL_STYLES or style=='italic_footer':return None
    width=max(spec['face'].getbbox(row)[2]-spec['face'].getbbox(row)[0]
              for row in spec['rows'])
    if style in ('italic_photo','italic_photo_fade'):
        label=font(21,'SemiBold').getbbox('PRIMJER')
        width=max(width,label[2]-label[0])
    return width


def block_gap(first, second):
    return EXAMPLE_BLOCK_GAP if 'example' in (first, second) else MIN_BLOCK_GAP


def validate_current_design(card, plan):
    """Fresh feed eligibility; legacy renderer remains available for archives.

    Enforced for initial proposals, repairs and every local recovery candidate.
    Explicitly retained finished JPEGs are not redesigned by this policy.
    """
    if plan.get('design')!='hybrid' or (plan.get('photo_window') is not None
            and (card['kind']!='quiz' or card.get('quiz_format')!='visual_identification')):
        raise ValueError('Separate photo layouts are reserved for picture-identification quizzes')
    if plan.get('heading_fade','standard')!='standard':
        raise ValueError('Fresh title shades require smooth edges')
    if any(b.get('style')=='overlay_light' for b in plan.get('blocks',())):
        raise ValueError('Fresh underline panels use minimal_rule; overlay_light is archive-only')
    if card.get('quiz_format')=='visual_identification':
        validate_visual_answers(card,plan['blocks'])


def validate_visual_answers(card, blocks):
    """Aligned answer groups for separate photos; multiple arrangements remain.

    Rows may have different counts (including two above a centred third), but
    share one centre line, consistent cells/type and equal clear row gaps.
    """
    if not blocks:return
    first=blocks[0]
    if any(any(b.get(k)!=first.get(k) for k in ('width','font_size','line_spacing')) for b in blocks):
        raise ValueError('Visual quiz answers require consistent widths and typography')
    rows={}
    for block in blocks:
        height=block_spec(card,block['role'],block['width'],block['style'],block['font_size'],
                          block['line_spacing'],block.get('max_lines'),block.get('wrapping','balanced'))['height']
        rows.setdefault(block['y'],[]).append({**block,'bottom':block['y']+height})
    groups=list(rows.values());centres=[]
    for group in groups:
        xs=[b['x'] for b in group]
        gaps=[b-a-first['width'] for a,b in zip(xs,xs[1:])]
        if gaps and max(gaps)-min(gaps)>1:
            raise ValueError('Visual quiz answers require aligned groups and consistent spacing')
        centres.append((xs[0]+xs[-1]+first['width'])/2)
    gaps=[b[0]['y']-max(a['bottom'] for a in group)
          for group,b in zip(groups,groups[1:])]
    if max(centres)-min(centres)>1 or (gaps and max(gaps)-min(gaps)>1):
        raise ValueError('Visual quiz answers require aligned groups and consistent spacing')


def measured_plan(card, plan):
    """Reject off-canvas, overlapping, unreadable, or mismatched proposals."""
    from .visual_placement import CARD_SCHEMA
    from jsonschema import Draft202012Validator
    if list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)):
        raise ValueError('Invalid hybrid composition contract')
    if [b['role'] for b in plan['blocks']] != roles(card):
        raise ValueError('Composition must preserve every reviewed block and quiz label order')
    if plan['photo_window'] is not None and plan.get('heading_tone','auto')!='auto':
        raise ValueError('Paper headings require automatic palette ink')
    if plan['photo_window'] is not None and plan.get('heading_fade')=='defined':
        raise ValueError('Paper headings cannot select a photographic shade')
    if plan.get('heading_shade','gentle')=='stronger' and (card['kind']!='quiz' or plan['photo_window'] is not None):
        raise ValueError('Stronger title shading requires a photographic quiz')
    header_end = heading(card)[2]
    if plan.get('heading_shade')=='emphasis' and (
            card['kind'] not in ('lesson','word') or plan['photo_window'] is not None
            or title_example_proximity(plan['blocks'],header_end)!='far'):
        raise ValueError('Decorative non-quiz title shading requires distant PRIMJER on a full photograph')
    measured=[]
    for block in plan['blocks']:
        spec=block_spec(card,block['role'],block['width'],block['style'],block['font_size'],
                        block['line_spacing'],block.get('max_lines'),block.get('wrapping','balanced'))
        style=block['style']
        if style!='italic_photo_fade' and block.get('fade_style') in ('defined','sharp'):
            raise ValueError('Only photographic faded examples can select a shade preset')
        if style!='italic_photo_fade' and block.get('shade_strength','soft')!='soft':
            raise ValueError('Only photographic faded examples can select shade strength')
        if style=='plain' and block.get('panel_opacity',100) not in (100,'solid'):
            raise ValueError('Unboxed editorial body cannot set panel opacity')
        if style=='plain' and block.get('panel_tone','auto')!='auto':
            raise ValueError('Unboxed editorial body requires automatic palette ink')
        if plan['design']=='editorial':
            if card['kind']=='quiz' or style!=('italic_footer' if block['role']=='example' else 'plain'):
                raise ValueError('Editorial requires plain explanation and italic footer')
            if block.get('photo_tone','auto')!='auto':
                raise ValueError('Paper examples require automatic palette ink')
        elif style in ('plain','italic_footer'):
            raise ValueError('Paper styles require the editorial design')
        if style=='bottom_sheet' and (block['width']<660 or block['y']<700):
            raise ValueError('Bottom sheet requires a wide lower placement')
        box=[block['x'],block['y'],block['x']+block['width'],block['y']+spec['height']]
        visible_width=occupied_width(spec)
        occupied=[*box[:2],box[0]+min(block['width'],visible_width) if visible_width is not None else box[2],box[3]]
        footer=style=='italic_footer'
        if box[0]<64 or box[2]>(880 if footer else 1016) or box[1]<header_end+24 or box[3]>(1286 if footer else 1170):
            raise ValueError('Composition intersects the fixed heading, margin or logo strip')
        for previous in measured:
            a=previous['occupied_bounds'];gap=block_gap(block['role'],previous['role'])
            if (occupied[0]<a[2]+gap and occupied[2]>a[0]-gap
                    and occupied[1]<a[3]+gap and occupied[3]>a[1]-gap):
                raise ValueError('Composition text blocks overlap or have no breathing room')
        measured.append({**block,**spec,'bounds':box,'occupied_bounds':occupied})
    if card['kind']=='quiz':
        if plan['design']!='hybrid' or (plan['photo_window'] is not None and card.get('quiz_format')!='visual_identification'):
            raise ValueError('Quiz photo treatment is fixed by its reviewed task type')
        if [(b['y'],b['x']) for b in measured] != sorted((b['y'],b['x']) for b in measured):
            raise ValueError('Quiz choices must retain their visual reading order')
    panel_area=sum((b['bounds'][2]-b['bounds'][0])*b['height'] for b in measured if b['style'] in PANEL_STYLES)
    if panel_area>WIDTH*HEIGHT*.49:
        raise ValueError('Hybrid copy covers too much of the photograph; never shrink/truncate')
    window=plan['photo_window']
    if plan['design']=='editorial' and (window is None or window['fit']!='cover'):
        raise ValueError('Editorial requires a wide cover-fit photograph')
    if plan['design']=='hybrid' and window is not None and window['fit']!='contain':
        raise ValueError('Hybrid separate photograph must remain complete')
    if window is not None:
        if window['y']<header_end+24 or window['y']+window['height']>1170:
            raise ValueError('Photo window intersects heading or logo strip')
        if window['height']<400 and card.get('quiz_format')!='visual_identification':
            raise ValueError('Only visual quizzes support smaller complete photo windows')
        for block in measured:
            if card.get('quiz_format')=='visual_identification' and block['y']<window['y']+window['height']+24:
                raise ValueError('Visual quiz answers must follow the complete photograph')
            if plan['design']=='editorial':
                if block['role']=='body' and block['bounds'][3]+24>window['y']:
                    raise ValueError('Editorial explanation must precede the photograph')
                if block['role']=='example' and block['y']<window['y']+window['height']+24:
                    raise ValueError('Editorial italic footer must follow the photograph')
            if block['role']!='example' and not (block['bounds'][3]+24<=window['y'] or block['y']>=window['y']+window['height']+24):
                raise ValueError('Separate photograph must remain free of explanation panels')
    if card.get('quiz_format')=='visual_identification' and (window is None or window['fit']!='contain'):
        raise ValueError('Visual quiz requires a complete protected photograph')
    return measured


def photo_colours(palette, tone='auto'):
    """Only catalogue colours and fixed fade backgrounds; no model primitives."""
    if tone not in PHOTO_TONES:raise ValueError('Unsupported photographic colour treatment')
    paper,ink,accent=palette['panel'],palette['ink'],palette['accent']
    if tone=='auto':return ['#ffffff','#000000'],None
    colour,backing={
        'paper_dark':('#ffffff','#000000'), 'ink_light':('#000000','#ffffff'),
        'paper_ink':(paper,ink), 'ink_paper':(ink,paper), 'accent_ink':(accent,ink),
        'ink_accent':(ink,accent), 'accent_dark':(accent,'#000000'),
        'accent_light':(accent,'#ffffff'), 'paper_accent':(paper,accent),
    }[tone]
    rgb=tuple(int(backing[i:i+2],16) for i in (1,3,5))
    return [colour],[(colour,rgb)]


def title_colours(palette,tone='auto'):
    """Title text keeps its approved colour; every title backing is neutral."""
    colours,_=photo_colours(palette,tone)
    if tone=='auto':return colours,None
    # Read older paired-tone IDs too, without restoring coloured title fades.
    white=tone in ('ink_light','ink_paper','ink_accent','accent_light')
    backing=(255,255,255) if white else (0,0,0)
    return colours,[(colours[0],backing)]


def protect_text(image, xy, rows, face, colours, threshold, region_limit=None, extra=(), line_spacing=None, allow_fade=True, backings=None, fade_style='standard', feather=None, bottom_padding=0, shade_levels=(90,130,170,210,240), feather_power=1, surround_opacity=1, light_shade_levels=None, light_surround_opacity=None, minimum_shade=0, top_padding=0, maximum_shade=255):
    """Real glyph contrast with approved shades, never an example box."""
    if fade_style not in FADE_STYLES:raise ValueError('Unsupported fade treatment')
    feather=PHOTO_FADE_FEATHER if feather is None else feather
    text_height,_=measure(rows,face,line_spacing)
    mask=Image.new('L',image.size)
    draw_rows(ImageDraw.Draw(mask),xy,rows,face,255,line_spacing)
    for extra_xy,extra_rows,extra_face in extra:
        draw_rows(ImageDraw.Draw(mask),extra_xy,extra_rows,extra_face,255)
    text_top=min([xy[1],*(item[0][1] for item in extra)])
    text_bottom=max([xy[1]+text_height,*(item[0][1]+measure(item[1],item[2])[0] for item in extra)])
    points=[(x,y) for y in range(max(0,int(text_top)),min(image.height,int(text_bottom+2)),3)
            for x in range(max(0,int(xy[0])-3),image.width,3) if mask.getpixel((x,y))>128]
    def lowest(candidate, colour):
        return min((contrast(colour,candidate.getpixel(p)) for p in points),default=10)
    choices=[(lowest(image,c),c) for c in colours]
    score,colour=max(choices)
    if score>=threshold and not minimum_shade:return colour,score,0
    if not allow_fade:raise ValueError('Unshaded photo text fails measured contrast')
    # A fixed neutral/palette shade protects only this text region.
    # Never recolour the scene to fit the selected accent.
    best=None
    left,top,right,bottom=region_limit or (0,0,WIDTH,HEIGHT)
    def surrounding_mask(opacity):
        if opacity>=1:return None
        # Renderer-only opacity profile, never a model-supplied drawing rule.
        # One bright glyph must not darken an otherwise empty full-width band.
        box=mask.getbbox();values=[]
        for x in range(image.width):
            distance=max(box[0]-20-x,x-box[2]-20,0)
            t=min(1,distance/TITLE_SURROUND_FEATHER);t=t*t*(3-2*t)
            values.append(round(255*(1-(1-opacity)*t)))
        result=Image.new('L',(image.width,1));result.putdata(values)
        return result.resize(image.size,Image.Resampling.NEAREST)
    surround_mask=surrounding_mask(surround_opacity)
    light_surround_mask=(surrounding_mask(light_surround_opacity)
                         if light_surround_opacity is not None else surround_mask)
    soft_mask=None
    if fade_style=='soft':
        # A compact, four-sided feather around the exact glyph region, rather
        # than a broad full-width strip. Its blur/extent remain trusted presets.
        box=mask.getbbox();soft_mask=Image.new('L',image.size)
        ImageDraw.Draw(soft_mask).rounded_rectangle((box[0]-28,box[1]-22,box[2]+28,box[3]+22),radius=24,fill=255)
        soft_mask=soft_mask.filter(ImageFilter.GaussianBlur(16))
        allowed=Image.new('L',image.size)
        ImageDraw.Draw(allowed).rectangle((left,top,right-1,bottom-1),fill=255)
        soft_mask=ImageChops.multiply(soft_mask,allowed)
    # Only trusted callers select these presets, never model-supplied fields.
    # Examples retain their contrast-driven strengths; the selected trusted
    # preset controls whether the lower edge tapers or stays crisp.
    for colour,backing in (backings if backings is not None else ((colours[0],(0,0,0)),(colours[-1],(255,255,255)))):
        white=backing==(255,255,255)
        levels=light_shade_levels if white and light_shade_levels is not None else shade_levels
        current_surround=light_surround_mask if white else surround_mask
        for alpha in levels:
            if alpha<minimum_shade or alpha>maximum_shade:continue
            overlay=Image.new('RGBA',image.size)
            if fade_style=='sharp':
                # Blend only the upper edge into the photograph. The lower
                # boundary stays crisp, with padding beyond the last row.
                od=ImageDraw.Draw(overlay)
                band_top=max(round(top),int(text_top)-SHARP_EXAMPLE_TOP_PADDING)
                band_bottom=min(round(bottom)-1,round(text_bottom+bottom_padding))
                fade_start=max(round(top),band_top-PHOTO_FADE_FEATHER)
                if band_top-fade_start<SHARP_EXAMPLE_TOP_PADDING:
                    # Near a protected boundary, use the available space up to
                    # the label rather than clipping a solid shade into a seam.
                    band_top=int(text_top)
                for y in range(fade_start,band_top):
                    t=(y-fade_start)/max(1,band_top-fade_start)
                    opacity=round(alpha*t*t*(3-2*t))
                    if opacity:od.line((left,y,right-1,y),fill=(*backing,opacity))
                od.rectangle((left,band_top,right-1,band_bottom),fill=(*backing,alpha))
            elif fade_style=='soft' and soft_mask is not None:
                overlay.paste((*backing,255),(0,0,*image.size))
                overlay.putalpha(soft_mask.point([round(v*alpha/255) for v in range(256)]))
            else:
                od=ImageDraw.Draw(overlay)
                for y in range(round(top),round(bottom)):
                    if fade_style=='defined':
                        # Retain the earlier linear, more defined strip. Padding
                        # belongs to both presets; never stop at the last glyph.
                        distance=max(text_top-y,y-text_bottom-bottom_padding,0)
                        opacity=round(alpha*max(0,1-distance/feather))
                        if opacity:od.line((left,y,right-1,y),fill=(*backing,opacity))
                        continue
                    # Taper to zero INSIDE protected bounds rather than clipping
                    # a still-opaque gradient into a visible horizontal seam.
                    core_start=max(top,text_top-top_padding)
                    start=max(top,core_start-feather);end=min(bottom-1,text_bottom+bottom_padding+feather)
                    core_end=min(text_bottom+bottom_padding,max(text_bottom,end-16))
                    if y<=start or y>=end:t=0
                    elif y<core_start:t=(y-start)/max(1,core_start-start)
                    elif y>core_end:t=(end-y)/max(1,end-core_end)
                    else:t=1
                    t=max(0,min(1,t));opacity=round(alpha*(t*t*(3-2*t))**feather_power)
                    if opacity:od.line((left,y,right-1,y),fill=(*backing,opacity))
            if current_surround is not None:
                overlay.putalpha(ImageChops.multiply(overlay.getchannel('A'),current_surround))
            candidate=Image.alpha_composite(image,overlay)
            score=lowest(candidate,colour)
            if score>=threshold:
                if best is None or alpha<best[0]:best=(alpha,candidate,colour,score)
                break
    if best is None:
        if maximum_shade<255:raise ValueError('Non-quiz title cannot remain readable within its shade limit')
        raise ValueError('Actual photographic text contrast fails; never publish unreadable copy')
    alpha,candidate,colour,score=best;image.paste(candidate)
    return colour,score,alpha


def category_label(image, label, palette, style='rounded', top=CATEGORY_TOP, paper_surface=False, tone='auto'):
    """Six fixed category treatments, shared anchors/typography and exact accents."""
    if style not in CATEGORY_STYLES:raise ValueError('Unsupported category treatment')
    face=font(27,'SemiBold');width=round(face.getlength(label))+46
    x=64;right=x+width;bottom=top+CATEGORY_HEIGHT
    ink,paper,accent=palette['ink'],palette['panel'],palette['accent']
    text_colour,surface=panel_colours(palette,tone)
    if tone=='auto':text_colour,surface=ink,paper if style=='outlined' else accent
    draw=ImageDraw.Draw(image)
    if style=='underlined':
        xy=(x,top+18)
        if paper_surface:
            colour=ink if tone=='auto' else text_colour;score=contrast(colour,paper);shade=0
            if score<4.5:raise ValueError('Category text fails measured contrast')
        else:
            try:
                colour,score,shade=protect_text(image,xy,[label],face,
                    [paper,ink] if tone=='auto' else [text_colour],4.5,allow_fade=False)
            except ValueError as error:
                raise ValueError('Category text fails measured contrast') from error
        draw=ImageDraw.Draw(image)
        draw_rows(draw,xy,[label],face,colour)
        draw.line((x,bottom-1,right-46,bottom-1),fill=accent,width=3)
        return {'style':style,'colour':colour,'contrast':round(score,2),'shading':shade}
    if style in ('rounded','pill'):
        draw.rounded_rectangle((x,top,right,bottom),radius=16 if style=='rounded' else 31,fill=surface)
    elif style=='ribbon':
        draw.polygon(((x,top),(right,top),(right+18,top+31),(right,bottom),(x,bottom)),fill=surface)
    elif style=='outlined':draw.rectangle((x,top,right,bottom),fill=surface,outline=accent,width=3)
    elif style=='tab':
        draw.rectangle((x,top,right,bottom),fill=surface)
        draw.line((x+23,bottom-9,right-23,bottom-9),fill=text_colour,width=2)
    if contrast(text_colour,surface)<4.5:raise ValueError('Category text fails measured contrast')
    centered(draw,(x,top,right,bottom),label,face,text_colour)
    return {'style':style,'colour':text_colour,'contrast':round(contrast(text_colour,surface),2),'shading':0}


def draw_panel(image, block, palette):
    """Approved panel treatments have distinct geometry/surfaces, never model primitives."""
    ink,paper,accent=palette['ink'],palette['panel'],palette['accent']
    x,y=block['x'],block['y'];right,bottom=block['bounds'][2:]
    style=block['style'];role=block['role'];padding=block['padding']
    colour,surface_colour=panel_colours(palette,block.get('panel_tone','auto'),dark=style=='overlay_dark')
    # Composite only the bounded surface. Glyphs, decorations and answer badges
    # remain opaque; geometry and renderer-owned drawing presets do not change.
    alpha=panel_alpha(block['panel_opacity']) if 'panel_opacity' in block else (235 if style=='overlay_light' else 255)
    surface=Image.new('RGBA',image.size)
    paint=ImageDraw.Draw(surface)
    fill=(*tuple(int(surface_colour[i:i+2],16) for i in (1,3,5)),alpha)
    if style in ('rounded','rounded_plain','pill'):
        radius={'rounded':24,'rounded_plain':36}.get(style,block['height']/2)
        paint.rounded_rectangle((x,y,right,bottom),radius=radius,fill=fill)
    elif style=='bottom_sheet':
        paint.rounded_rectangle((x,y,right,bottom),radius=54,fill=fill)
        paint.rectangle((x,y+54,right,bottom),fill=fill)
    elif style=='soft_corner':
        paint.rounded_rectangle((x,y,right,bottom),radius=46,fill=fill)
        paint.rectangle((x,y+46,x+46,bottom),fill=fill)
    elif style=='folded_corner':
        paint.polygon(((x,y),(right-24,y),(right,y+24),(right,bottom),(x,bottom)),fill=fill)
    elif style in PANEL_STYLES:paint.rectangle((x,y,right,bottom),fill=fill)
    else:raise ValueError('Unsupported trusted panel renderer')
    image.paste(Image.alpha_composite(image,surface))
    draw=ImageDraw.Draw(image)
    if style=='outlined':draw.rectangle((x,y,right,bottom),outline=accent,width=3)
    elif style=='overlay_light':
        draw.line((x+padding,bottom-12,right-padding,bottom-12),fill=accent,width=2)
    elif style=='side_rule':
        draw.rectangle((x,y,x+12,bottom),fill=accent)
    elif style=='bottom_sheet':
        mid=(x+right)/2;draw.rounded_rectangle((mid-32,y+10,mid+32,y+15),radius=2,fill=accent)
    elif style=='split_panel':
        draw.rectangle((x,y,x+82,bottom),fill=accent)
        if role=='body':
            draw.line((x+28,y+padding,x+54,y+padding),fill=ink,width=4)
            draw.line((x+28,y+padding+14,x+54,y+padding+14),fill=ink,width=4)
    elif style=='minimal_rule':
        draw.line((x,bottom-2,right,bottom-2),fill=accent,width=5)
    elif style=='double_frame':
        draw.rectangle((x,y,right,bottom),outline=accent,width=4)
        draw.rectangle((x+10,y+10,right-10,bottom-10),outline=ink,width=1)
    elif style=='notebook_margin':
        draw.line((x+12,y+12,x+12,bottom-12),fill=accent,width=3)
        for tick_y in range(round(y+18),round(bottom-12),16):
            draw.line((x+3,tick_y,x+8,tick_y),fill=accent,width=2)
    elif style=='top_ribbon':
        draw.rectangle((x,y,right,y+8),fill=accent)
        draw.line((x+padding,bottom-10,right-padding,bottom-10),fill=ink,width=1)
    elif style=='corner_brackets':
        for corner_x,direction_x in ((x+8,1),(right-8,-1)):
            for corner_y,direction_y in ((y+8,1),(bottom-8,-1)):
                draw.line((corner_x+32*direction_x,corner_y,corner_x,corner_y,
                           corner_x,corner_y+24*direction_y),fill=accent,width=3)
    elif style=='soft_corner':
        rule_x=x+18+(block.get('content_offset',0) if role!='body' else 0)
        draw.line((rule_x,y+padding,rule_x,bottom-padding),fill=accent,width=4)
    elif style=='folded_corner':
        draw.line((x+3,y+3,right-26,y+3,right-3,y+26),fill=accent,width=3)
        draw.polygon(((right-24,y),(right-24,y+24),(right,y+24)),fill=accent)
    if role=='body' and style in ('rounded','outlined'):
        draw.rounded_rectangle((x+18,y+padding,x+23,bottom-padding),radius=2,fill=accent)
    if role!='body':
        marker_style=block.get('marker_style','circle')
        if marker_style not in MARKER_STYLES:raise ValueError('Unsupported answer badge')
        marker_x=x+(15 if style=='split_panel' else 20)+block.get('content_offset',0)
        marker=(marker_x,
                y+(block['height']-52)/2,
                marker_x+52,
                y+(block['height']+52)/2)
        badge_fill=paper if style in ('overlay_dark','split_panel') else accent
        if block.get('panel_tone','auto')!='auto' and badge_fill==surface_colour:badge_fill=paper
        label_colour=ink
        if marker_style=='circle':draw.ellipse(marker,fill=badge_fill)
        elif marker_style=='rounded_square':draw.rounded_rectangle(marker,radius=14,fill=badge_fill)
        elif marker_style=='square':draw.rectangle(marker,fill=badge_fill)
        else:
            mid_x=(marker[0]+marker[2])/2;mid_y=(marker[1]+marker[3])/2
            draw.polygon(((mid_x,mid_y-30),(mid_x+32,mid_y+30),(mid_x-32,mid_y+30)),fill=badge_fill)
            marker=(marker[0],marker[1]+9,marker[2],marker[3]+9)
        centered(draw,marker,role,font(24 if marker_style=='triangle' else 28,'Bold'),label_colour)
    return colour


def render_hybrid(card, palette_id, background, output, plan=None):
    catalogue=json.loads((ROOT/'data/design-palettes.json').read_text())
    if palette_id not in catalogue:raise ValueError('Unknown approved palette')
    palette=catalogue[palette_id]
    plan=copy.deepcopy(plan) if plan is not None else default_plan(card)
    if plan.get('palette',palette_id)!=palette_id:raise ValueError('Composition palette differs from rendering palette')
    blocks=measured_plan(card,plan)
    ink,accent,paper=palette['ink'],palette['accent'],palette['panel']
    body_contrast=min(contrast(ink,paper),contrast(ink,accent))
    if body_contrast<4.5:raise ValueError('Hybrid palette fails text contrast')
    with Image.open(background) as original:
        photo=original.convert('RGB')
    window=plan['photo_window'];photo_bounds=None
    if window:
        image=Image.new('RGBA',(WIDTH,HEIGHT),paper)
        inset=(ImageOps.fit(photo,(952,window['height']),method=Image.Resampling.LANCZOS,centering=(.5,.58))
               if window['fit']=='cover' else ImageOps.contain(photo,(952,window['height']),Image.Resampling.LANCZOS))
        photo_bounds=[(WIDTH-inset.width)//2,window['y'],(WIDTH+inset.width)//2,window['y']+inset.height]
        mask=Image.new('L',inset.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,inset.width-1,inset.height-1),radius=28,fill=255)
        image.paste(inset,photo_bounds[:2],mask)
        for block in blocks:
            if block['style'] in ('italic_photo','italic_photo_fade') and not (block['x']>=photo_bounds[0]+20 and block['bounds'][2]<=photo_bounds[2]-20
                    and block['y']>=photo_bounds[1]+20 and block['bounds'][3]<=photo_bounds[3]-20):
                raise ValueError('Italic example must fit directly inside the complete photograph')
    else:
        image=ImageOps.fit(photo,(WIDTH,HEIGHT),method=Image.Resampling.LANCZOS).convert('RGBA')
    title_face,title_rows,header_end=heading(card)
    if window and card.get('quiz_format')=='visual_identification':
        for block in blocks:
            if block['role'] in ('body','example') or block['style']=='split_panel':continue
            # Centre the visible badge+text group, not merely an invisible wide
            # panel. A paper-coloured panel can blend into the page completely.
            text_right=block['text_inset']+max(block['face'].getlength(row) for row in block['rows'])
            marker_left=14 if block.get('marker_style')=='triangle' else 20
            block['content_offset']=(block['width']-(text_right-marker_left))/2-marker_left
    heading_tone=plan.get('heading_tone','auto')
    heading_backing=None
    if window:heading_colour,heading_contrast,heading_shading=ink,contrast(ink,paper),0
    else:
        colours,backings=title_colours(palette,heading_tone)
        near_example=title_example_proximity(blocks,header_end)=='near'
        title_cap=(255 if card['kind']=='quiz' else
                   NEAR_EXAMPLE_TITLE_MAX_SHADE if near_example else NONQUIZ_TITLE_MAX_SHADE)
        minimum_shade=(QUIZ_TITLE_MIN_SHADE if plan.get('heading_shade','gentle')=='stronger' else
                       TITLE_SHADE_LEVELS[0] if plan.get('heading_shade')=='emphasis' else 0)
        # Equal upper/lower fades may reach the category area. Category
        # elements are drawn after all photographic shades, always on top.
        heading_colour,heading_contrast,heading_shading=protect_text(image,(64,HEADING_TOP),title_rows,title_face,colours,3,
            (0,0,WIDTH,HEIGHT),backings=backings,
            fade_style=plan.get('heading_fade','standard'),feather=TITLE_FADE_FEATHER,
            top_padding=TITLE_FADE_PADDING,bottom_padding=TITLE_FADE_PADDING,
            shade_levels=TITLE_SHADE_LEVELS,feather_power=TITLE_FADE_POWER,
            surround_opacity=TITLE_SURROUND_OPACITY,light_shade_levels=TITLE_WHITE_SHADE_LEVELS,
            light_surround_opacity=TITLE_WHITE_SURROUND_OPACITY,
            minimum_shade=minimum_shade,
            maximum_shade=title_cap)
        if heading_shading:
            heading_backing=('#000000' if heading_colour=='#ffffff' else '#ffffff') if heading_tone=='auto' else '#ffffff' if backings[0][1]==(255,255,255) else '#000000'
    example_contrast=None;example_shading=0;example_colour=None
    # Apply photographic shading before drawing any panels or heading glyphs,
    # so a nearby example's fade cannot wash out an already-rendered panel.
    for block in blocks:
        if block['style'] in ('italic_photo','italic_photo_fade'):
            x,y=block['x'],block['y'];label_face=font(21,'SemiBold')
            example_y=y+measure(['PRIMJER'],label_face)[0]+16
            # Text remains above y1170. Its background fade may taper into
            # the footer; the untouched logo is composited on top afterward.
            limit=photo_bounds or [0,header_end+14,WIDTH,HEIGHT-64]
            colours,backings=photo_colours(palette,block.get('photo_tone','auto'))
            example_colour,example_contrast,example_shading=protect_text(
                image,(x,example_y),block['rows'],block['face'],colours,4.5,limit,
                extra=[((x,y),['PRIMJER'],label_face)],
                line_spacing=block['line_spacing'],allow_fade=block['style']!='italic_photo',backings=backings,fade_style=block.get('fade_style','standard'),bottom_padding=EXAMPLE_FADE_PADDING,
                shade_levels=EXAMPLE_SHADE_LEVELS if 'shade_strength' in block else (90,130,170,210,240),
                minimum_shade=EXAMPLE_SHADE_MINIMUMS[block['shade_strength']]
                    if block['style']=='italic_photo_fade' and 'shade_strength' in block else 0)
            block['photo_colour']=example_colour;block['photo_contrast']=example_contrast
            block['photo_shading']=example_shading
    # Another block's preset fade must not invalidate already-chosen glyph
    # colours. Validate the final photographic surface before drawing anything.
    if not window:
        protect_text(image,(64,HEADING_TOP),title_rows,title_face,[heading_colour],3,allow_fade=False)
    for block in blocks:
        if 'photo_colour' not in block:continue
        x,y=block['x'],block['y'];label_face=font(21,'SemiBold')
        is_example=block['role']=='example'
        text_y=y+measure(['PRIMJER'],label_face)[0]+16 if is_example else y
        _,score,_=protect_text(image,(x,text_y),block['rows'],block['face'],[block['photo_colour']],4.5,
            extra=[((x,y),['PRIMJER'],label_face)] if is_example else [],
            line_spacing=block['line_spacing'],allow_fade=False)
        if is_example:example_contrast=score;example_shading=block['photo_shading']
        else:body_contrast=min(body_contrast,score)
    draw=ImageDraw.Draw(image)
    label=LABELS[card['kind']]
    category=category_label(image,label,palette,plan.get('category_style','underlined' if plan['design']=='editorial' else 'rounded'),paper_surface=bool(window),tone=plan.get('category_tone','auto'))
    draw=ImageDraw.Draw(image)
    draw_rows(draw,(64,HEADING_TOP),title_rows,title_face,heading_colour)
    for block in blocks:
        x,y=block['x'],block['y'];role=block['role'];face=block['face'];rows=block['rows'];padding=block['padding'];style=block['style']
        leading=block['line_spacing']
        if role=='example':
            label_face=font(21,'SemiBold');label_height=measure(['PRIMJER'],label_face)[0]
            colour=block.get('photo_colour',ink)
            if style=='italic_footer':
                draw.line((x,y,x+block['width'],y),fill=accent,width=2);y+=24
                example_contrast=contrast(ink,paper)
            draw_rows(draw,(x,y),['PRIMJER'],label_face,colour)
            draw_rows(draw,(x,y+label_height+16),rows,face,colour,leading)
        elif style=='plain':
            draw_rows(draw,(x,y),rows,face,ink,leading)
        else:
            colour=draw_panel(image,block,palette)
            draw=ImageDraw.Draw(image)
            text_y=(y+padding if role=='body' else
                    y+(block['height']-block['text_cell_height'])/2+block['text_cell_offset'])
            text_x=x+block['text_inset']+block.get('content_offset',0)
            # Actual composited glyph contrast, without repairing opacity or fades.
            try:
                _,score,_=protect_text(image,(text_x,text_y),rows,face,[colour],4.5,
                                      line_spacing=leading,allow_fade=False)
            except ValueError as error:
                raise ValueError('Actual panel text contrast fails; never publish unreadable copy') from error
            body_contrast=min(body_contrast,score)
            draw_rows(draw,(text_x,text_y),rows,face,colour,leading)
    with Image.open(ROOT/'assets/watermark.png') as source:
        if source.mode!='RGBA' or source.getextrema()[3][0]!=0 or source.getextrema()[3][1]==0:
            raise ValueError('Original logo must retain alpha transparency')
        logo=source.crop(source.getchannel('A').getbbox());logo.thumbnail((112,92),Image.Resampling.LANCZOS)
    image.alpha_composite(logo,(WIDTH-64-logo.width,HEIGHT-64-logo.height))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(output,'JPEG',quality=94,subsampling=0,optimize=True)
    return {'size':[WIDTH,HEIGHT],
            **({'treatment':'B','question_bounds':[64,HEADING_TOP,1016,header_end],
                'photo_size':[photo_bounds[2]-photo_bounds[0],photo_bounds[3]-photo_bounds[1]]} if card.get('quiz_format')=='visual_identification' else {}),
            'typography':'hybrid','palette':palette_id,'panel_position':'free' if plan['confidence']=='high' else 'normal',
            'composition':plan,'design':plan['design'],'block_styles':{b['role']:b['style'] for b in blocks},'body_font_size':next((b['size'] for b in blocks if b['role']!='example'),density(card)[0]),
            'category_style':category['style'],'category_contrast':category['contrast'],
            'heading_tone':heading_tone,'heading_colour':heading_colour,
            'heading_backing':heading_backing,
            'example_tone':next((b.get('photo_tone','auto') for b in blocks if b['role']=='example'),None),'example_colour':example_colour,
            'answer_badges':{b['role']:b.get('marker_style','circle') for b in blocks if b['role'] not in ('body','example')},
            'block_typography':{b['role']:{k:b[k] for k in ('font_size','line_spacing','max_lines','wrapping')} for b in blocks},'heading_font':'Lora SemiBold','body_font':'Inter',
            'example_style':next(({'italic_photo':'Lora Italic over photograph','italic_photo_fade':'Lora Italic over photograph with approved fade','italic_footer':'Lora Italic on paper footer'}[b['style']] for b in blocks if b['role']=='example'),None),
            'panel_bounds':[list(map(round,b['bounds'])) for b in blocks if b['style'] in PANEL_STYLES],
            'example_bounds':next((list(map(round,b['bounds'])) for b in blocks if b['role']=='example'),None),
            'photo_bounds':photo_bounds,'photo_cropped':not bool(window) or window['fit']=='cover',
            'body_contrast':round(body_contrast,2),'heading_contrast':round(heading_contrast,2),
            'example_contrast':round(example_contrast,2) if example_contrast else None,
            'heading_shading':heading_shading,'example_shading':example_shading}
