"""Measured photographic compositions from data, never model-generated drawing code."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .core import ROOT
from .render import (HEIGHT, WIDTH, MARGIN, LABELS, centered, contrast, density,
                     draw_rows, font, measure, wrap)


def serif(size, italic=False):
    face = ImageFont.truetype(str(ROOT/'assets/fonts'/('Lora-Italic.ttf' if italic else 'Lora.ttf')), size)
    face.set_variation_by_axes([400 if italic else 600])
    return face


def heading(card):
    face = serif(50 if card['kind']=='quiz' else 74)
    rows = wrap(card.get('question') if card['kind']=='quiz' else card['heading'], face, 952)
    if len(rows) > (3 if card['kind']=='quiz' else 2):
        raise ValueError('Hybrid heading exceeds measured lines; never truncate')
    return face, rows, 155 + measure(rows, face)[0]


def roles(card):
    return ([o['label'] for o in card['options']] if card['kind']=='quiz' else
            ['body'] + (['example'] if card.get('example') else []))


def block_spec(card, role, width):
    """The model chooses width/position; trusted code determines every text height."""
    size, padding = density(card)
    if role == 'example':
        face = serif(min(size, 36), italic=True)
        rows = wrap(card['example'], face, width)
        label_height = measure(['PRIMJER'], font(21, 'SemiBold'))[0]
        height = label_height + 16 + measure(rows, face)[0]
    else:
        face = font(size)
        text = card['body'] if role=='body' else next(o['text'] for o in card['options'] if o['label']==role)
        rows = wrap(text, face, width - (2*padding+24 if role=='body' else 118))
        height = max(92 if role!='body' else 0, measure(rows, face)[0] + 2*padding)
    return {'face':face, 'rows':rows, 'height':height, 'padding':padding, 'size':size}


def default_plan(card):
    """Safe deterministic hybrid when the single cosmetic model call is unavailable."""
    y = heading(card)[2] + 28
    blocks = []
    for role in roles(card):
        spec = block_spec(card, role, 952)
        blocks.append({'role':role, 'x':64, 'y':round(y), 'width':952})
        y += spec['height'] + (28 if role=='body' else 16)
    return {'confidence':'uncertain', 'photo_window':None, 'blocks':blocks}


def measured_plan(card, plan):
    """Reject off-canvas, overlapping, unreadable, or mismatched proposals."""
    from .visual_placement import CARD_SCHEMA
    from jsonschema import Draft202012Validator
    if list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)):
        raise ValueError('Invalid hybrid composition contract')
    if [b['role'] for b in plan['blocks']] != roles(card):
        raise ValueError('Composition must preserve every reviewed block and quiz label order')
    header_end = heading(card)[2]
    measured=[]
    for block in plan['blocks']:
        spec=block_spec(card, block['role'], block['width'])
        box=[block['x'],block['y'],block['x']+block['width'],block['y']+spec['height']]
        if box[0]<64 or box[2]>1016 or box[1]<header_end+24 or box[3]>1170:
            raise ValueError('Composition intersects the fixed heading, margin or logo strip')
        for previous in measured:
            a=previous['bounds']
            if box[0]<a[2]+14 and box[2]>a[0]-14 and box[1]<a[3]+14 and box[3]>a[1]-14:
                raise ValueError('Composition text blocks overlap or have no breathing room')
        measured.append({**block,**spec,'bounds':box})
    if card['kind']=='quiz':
        if plan['photo_window'] is not None:
            raise ValueError('Quiz photo treatment is fixed by its reviewed task type')
        if [(b['y'],b['x']) for b in measured] != sorted((b['y'],b['x']) for b in measured):
            raise ValueError('Quiz choices must retain their visual reading order')
    panel_area=sum((b['bounds'][2]-b['bounds'][0])*b['height'] for b in measured if b['role']!='example')
    if panel_area>WIDTH*HEIGHT*.49:
        raise ValueError('Hybrid copy covers too much of the photograph; never shrink/truncate')
    window=plan['photo_window']
    if window is not None:
        if window['y']<header_end+24 or window['y']+window['height']>1170:
            raise ValueError('Photo window intersects heading or logo strip')
        for block in measured:
            if block['role']=='body' and not (block['bounds'][3]+24<=window['y'] or block['y']>=window['y']+window['height']+24):
                raise ValueError('Separate photograph must remain free of explanation panels')
    return measured


def protect_text(image, xy, rows, face, colours, threshold, region_limit=None, extra=()):
    """Real glyph contrast, using a smooth neutral fade rather than an example box."""
    text_height,_=measure(rows,face)
    mask=Image.new('L',image.size)
    draw_rows(ImageDraw.Draw(mask),xy,rows,face,255)
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
    if score>=threshold:return colour,score,0
    # A neutral black/white feathered gradient protects only this text region.
    # Never recolour the scene to fit the selected accent.
    best=None
    left,top,right,bottom=region_limit or (0,0,WIDTH,HEIGHT)
    for colour,backing in ((colours[0],(0,0,0)),(colours[-1],(255,255,255))):
        for alpha in (90,130,170,210,240):
            overlay=Image.new('RGBA',image.size)
            od=ImageDraw.Draw(overlay)
            for y in range(round(top),round(bottom)):
                distance=max(text_top-y,y-text_bottom,0)
                opacity=round(alpha*max(0,1-distance/100))
                if opacity:od.line((left,y,right-1,y),fill=(*backing,opacity))
            candidate=Image.alpha_composite(image,overlay)
            score=lowest(candidate,colour)
            if score>=threshold:
                if best is None or alpha<best[0]:best=(alpha,candidate,colour,score)
                break
    if best is None:raise ValueError('Actual photographic text contrast fails; never publish unreadable copy')
    alpha,candidate,colour,score=best;image.paste(candidate)
    return colour,score,alpha


def render_hybrid(card, palette_id, background, output, plan=None):
    palette=json.loads((ROOT/'data/design-palettes.json').read_text())[palette_id]
    if card['kind']=='quiz' and card.get('quiz_format')=='visual_identification':
        from .story_layouts import visual_quiz_image
        result=visual_quiz_image(card,background,output,palette,height=HEIGHT,serif_heading=True)
        return {**result,'palette':palette_id,'panel_position':'separate_photo','typography':'hybrid'}
    plan=plan or default_plan(card);blocks=measured_plan(card,plan)
    ink,accent,paper=palette['ink'],palette['accent'],palette['panel']
    body_contrast=min(contrast(ink,paper),contrast(ink,accent))
    if body_contrast<4.5:raise ValueError('Hybrid palette fails text contrast')
    with Image.open(background) as original:
        photo=original.convert('RGB')
    window=plan['photo_window'];photo_bounds=None
    if window:
        image=Image.new('RGBA',(WIDTH,HEIGHT),paper)
        inset=ImageOps.contain(photo,(952,window['height']),Image.Resampling.LANCZOS)
        photo_bounds=[(WIDTH-inset.width)//2,window['y'],(WIDTH+inset.width)//2,window['y']+inset.height]
        mask=Image.new('L',inset.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,inset.width-1,inset.height-1),radius=28,fill=255)
        image.paste(inset,photo_bounds[:2],mask)
        for block in blocks:
            if block['role']=='example' and not (block['x']>=photo_bounds[0]+20 and block['bounds'][2]<=photo_bounds[2]-20
                    and block['y']>=photo_bounds[1]+20 and block['bounds'][3]<=photo_bounds[3]-20):
                raise ValueError('Italic example must fit directly inside the complete photograph')
    else:
        image=ImageOps.fit(photo,(WIDTH,HEIGHT),method=Image.Resampling.LANCZOS).convert('RGBA')
    title_face,title_rows,header_end=heading(card)
    if window:heading_colour,heading_contrast,heading_shading=ink,contrast(ink,paper),0
    else:
        heading_colour,heading_contrast,heading_shading=protect_text(image,(64,155),title_rows,title_face,[paper,ink],3)
    example_contrast=None;example_shading=0;example_colour=None
    # Apply photographic shading before drawing any panels or heading glyphs,
    # so a nearby example's fade cannot wash out an already-rendered panel.
    for block in blocks:
        if block['role']=='example':
            x,y=block['x'],block['y'];label_face=font(21,'SemiBold')
            example_y=y+measure(['PRIMJER'],label_face)[0]+16
            limit=photo_bounds or [0,header_end+14,WIDTH,1170]
            example_colour,example_contrast,example_shading=protect_text(
                image,(x,example_y),block['rows'],block['face'],[paper,ink],4.5,limit,
                extra=[((x,y),['PRIMJER'],label_face)])
    draw=ImageDraw.Draw(image)
    label_face=font(27,'SemiBold');label=LABELS[card['kind']]
    label_box=(64,64,64+round(label_face.getlength(label))+46,126)
    draw.rounded_rectangle(label_box,radius=16,fill=accent);centered(draw,label_box,label,label_face,ink)
    draw_rows(draw,(64,155),title_rows,title_face,heading_colour)
    for block in blocks:
        x,y=block['x'],block['y'];role=block['role'];face=block['face'];rows=block['rows'];padding=block['padding']
        if role=='example':
            label_face=font(21,'SemiBold');label_height=measure(['PRIMJER'],label_face)[0]
            example_y=y+label_height+16
            draw=ImageDraw.Draw(image)
            draw_rows(draw,(x,y),['PRIMJER'],label_face,example_colour)
            draw_rows(draw,(x,example_y),rows,face,example_colour)
        else:
            draw=ImageDraw.Draw(image)
            draw.rounded_rectangle(tuple(block['bounds']),radius=24,fill=paper)
            if role=='body':
                draw.rounded_rectangle((x+18,y+padding,x+23,block['bounds'][3]-padding),radius=2,fill=accent)
                draw_rows(draw,(x+padding+24,y+padding),rows,face,ink)
            else:
                marker=(x+20,y+(block['height']-52)/2,x+72,y+(block['height']+52)/2)
                draw.ellipse(marker,fill=accent);centered(draw,marker,role,font(28,'Bold'),ink)
                draw_rows(draw,(x+94,y+(block['height']-measure(rows,face)[0])/2),rows,face,ink)
    with Image.open(ROOT/'assets/watermark.png') as source:
        if source.mode!='RGBA' or source.getextrema()[3][0]!=0 or source.getextrema()[3][1]==0:
            raise ValueError('Original logo must retain alpha transparency')
        logo=source.crop(source.getchannel('A').getbbox());logo.thumbnail((112,92),Image.Resampling.LANCZOS)
    image.alpha_composite(logo,(WIDTH-64-logo.width,HEIGHT-64-logo.height))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(output,'JPEG',quality=94,subsampling=0,optimize=True)
    return {'size':[WIDTH,HEIGHT],'typography':'hybrid','palette':palette_id,'panel_position':'free' if plan['confidence']=='high' else 'normal',
            'composition':plan,'body_font_size':density(card)[0],'heading_font':'Lora SemiBold','body_font':'Inter',
            'example_style':'Lora Italic over photograph' if card.get('example') else None,
            'panel_bounds':[list(map(round,b['bounds'])) for b in blocks if b['role']!='example'],
            'example_bounds':next((list(map(round,b['bounds'])) for b in blocks if b['role']=='example'),None),
            'photo_bounds':photo_bounds,'photo_cropped':not bool(window),
            'body_contrast':round(body_contrast,2),'heading_contrast':round(heading_contrast,2),
            'example_contrast':round(example_contrast,2) if example_contrast else None,
            'heading_shading':heading_shading,'example_shading':example_shading}
