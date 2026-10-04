"""Measured photographic compositions from data, never model-generated drawing code."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .core import ROOT
from .designs import BODY_STYLES, EXAMPLE_STYLES, PANEL_STYLES, MARKER_STYLES, typography
from .render import (HEIGHT, WIDTH, LABELS, centered, contrast, density,
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


def block_spec(card, role, width, style=None, font_size=None, line_spacing=1.30,
               max_lines=None, wrapping='balanced'):
    """Only trusted fonts/presets; actual glyphs determine final height."""
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
        if style not in BODY_STYLES or (role!='body' and style in ('plain','caption')):
            raise ValueError('Unsupported explanation/answer style')
        face=font(size,'SemiBold' if style=='caption' else 'Regular')
        text=card['body'] if role=='body' else next(o['text'] for o in card['options'] if o['label']==role)
        inset=(0 if style in ('plain','caption') else
               (106 if style=='split_panel' else padding+24 if role=='body' else 94))
        text_width=width-inset-(0 if style in ('plain','caption') else padding)
        extra=0 if style=='plain' else 20 if style=='caption' else 2*padding
    rows=wrap(text,face,text_width,wrapping)
    if any(face.getbbox(row)[2]-face.getbbox(row)[0]>text_width for row in rows):
        raise ValueError('Actual glyphs exceed block width')
    if max_lines is not None and len(rows)>max_lines:raise ValueError('Exact text exceeds maximum lines; never truncate')
    if style=='caption' and len(rows)>3:raise ValueError('Caption treatment is limited to three measured lines')
    height=measure(rows,face,line_spacing)[0]+extra
    if role not in ('body','example'):height=max(92,height)
    return {'face':face,'rows':rows,'height':height,'padding':padding,'size':size,'style':style,
            'font_size':size,'line_spacing':line_spacing,'max_lines':max_lines,'wrapping':wrapping,'text_inset':inset}


def declared_block(card,role,width=952,style=None,**geometry):
    spec=block_spec(card,role,width,style)
    return {'role':role,'style':spec['style'],'width':width,'font_size':spec['size'],
            **({'marker_style':'circle'} if role not in ('body','example') else {}),
            'line_spacing':1.30,'max_lines':None,'wrapping':'balanced',**geometry}


def default_plan(card):
    """Deterministic measured fallback, never another model/image call."""
    y=heading(card)[2]+28;blocks=[];window=None
    if card.get('quiz_format')=='visual_identification':
        y=max(250,y)
        specs=[block_spec(card,role,952) for role in roles(card)]
        height=min(510,1170-y-28-sum(s['height'] for s in specs)-16*(len(specs)-1))
        if height<240:raise ValueError('Visual quiz cannot preserve complete photo and exact copy')
        window={'y':y,'height':height,'fit':'contain'};y+=height+28
    for role in roles(card):
        spec=block_spec(card,role,952)
        blocks.append(declared_block(card,role,x=64,y=round(y)))
        y+=spec['height']+(28 if role=='body' else 16)
    return {'confidence':'uncertain','design':'hybrid','photo_window':window,'blocks':blocks}


def editorial_plan(card):
    if card['kind']=='quiz':raise ValueError('Quiz retains its clear photographic design')
    top=heading(card)[2]+28
    body=declared_block(card,'body',style='plain',x=64,y=top)
    photo_top=top+block_spec(card,'body',952,'plain')['height']+24
    footer_height=block_spec(card,'example',800,'italic_footer')['height'] if card.get('example') else 0
    photo_height=min(560,1170-photo_top,1286-photo_top-footer_height-24)
    if photo_height<400:raise ValueError('Editorial reference cannot fit exact copy')
    blocks=[body]
    if card.get('example'):
        blocks.append(declared_block(card,'example',800,'italic_footer',x=64,y=photo_top+photo_height+24))
    return {'confidence':'high','design':'editorial','photo_window':{'y':photo_top,'height':photo_height,'fit':'cover'},'blocks':blocks}


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
        spec=block_spec(card,block['role'],block['width'],block['style'],block['font_size'],
                        block['line_spacing'],block.get('max_lines'),block.get('wrapping','balanced'))
        style=block['style']
        if plan['design']=='editorial':
            if card['kind']=='quiz' or style!=('italic_footer' if block['role']=='example' else 'plain'):
                raise ValueError('Editorial requires plain explanation and italic footer')
        elif style in ('plain','italic_footer'):
            raise ValueError('Paper styles require the editorial design')
        if style=='bottom_sheet' and (block['width']<660 or block['y']<700):
            raise ValueError('Bottom sheet requires a wide lower placement')
        box=[block['x'],block['y'],block['x']+block['width'],block['y']+spec['height']]
        footer=style=='italic_footer'
        if box[0]<64 or box[2]>(880 if footer else 1016) or box[1]<header_end+24 or box[3]>(1286 if footer else 1170):
            raise ValueError('Composition intersects the fixed heading, margin or logo strip')
        for previous in measured:
            a=previous['bounds']
            if box[0]<a[2]+14 and box[2]>a[0]-14 and box[1]<a[3]+14 and box[3]>a[1]-14:
                raise ValueError('Composition text blocks overlap or have no breathing room')
        measured.append({**block,**spec,'bounds':box})
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
        if any(b['style']=='caption' for b in measured):
            raise ValueError('Photographic caption requires a full-background hybrid card')
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


def protect_text(image, xy, rows, face, colours, threshold, region_limit=None, extra=(), line_spacing=None, allow_fade=True):
    """Real glyph contrast, using a smooth neutral fade rather than an example box."""
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
    if score>=threshold:return colour,score,0
    if not allow_fade:raise ValueError('Unshaded photo text fails measured contrast')
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


def draw_panel(image, block, palette):
    """Approved panel treatments have distinct geometry/surfaces, never model primitives."""
    ink,paper,accent=palette['ink'],palette['panel'],palette['accent']
    x,y=block['x'],block['y'];right,bottom=block['bounds'][2:]
    style=block['style'];role=block['role'];padding=block['padding']
    draw=ImageDraw.Draw(image);colour=ink
    if style=='rounded':draw.rounded_rectangle((x,y,right,bottom),radius=24,fill=paper)
    elif style=='outlined':draw.rectangle((x,y,right,bottom),fill=paper,outline=accent,width=3)
    elif style=='overlay_dark':
        draw.rectangle((x,y,right,bottom),fill=ink);colour=paper
    elif style=='overlay_light':
        overlay=Image.new('RGBA',image.size)
        rgb=tuple(int(paper[i:i+2],16) for i in (1,3,5))
        ImageDraw.Draw(overlay).rectangle((x,y,right,bottom),fill=(*rgb,235))
        image.paste(Image.alpha_composite(image,overlay));draw=ImageDraw.Draw(image)
        draw.line((x+padding,bottom-12,right-padding,bottom-12),fill=accent,width=2)
    elif style=='side_rule':
        draw.rectangle((x,y,right,bottom),fill=paper)
        draw.rectangle((x,y,x+12,bottom),fill=accent)
    elif style=='bottom_sheet':
        draw.rounded_rectangle((x,y,right,bottom),radius=54,fill=paper)
        draw.rectangle((x,y+54,right,bottom),fill=paper)
        mid=(x+right)/2;draw.rounded_rectangle((mid-32,y+10,mid+32,y+15),radius=2,fill=accent)
    elif style=='split_panel':
        draw.rectangle((x,y,right,bottom),fill=paper)
        draw.rectangle((x,y,x+82,bottom),fill=accent)
        if role=='body':
            draw.line((x+28,y+padding,x+54,y+padding),fill=ink,width=4)
            draw.line((x+28,y+padding+14,x+54,y+padding+14),fill=ink,width=4)
    elif style=='minimal_rule':
        draw.rectangle((x,y,right,bottom),fill=paper)
        draw.line((x,bottom-2,right,bottom-2),fill=accent,width=5)
    else:raise ValueError('Unsupported trusted panel renderer')
    if role=='body' and style in ('rounded','outlined'):
        draw.rounded_rectangle((x+18,y+padding,x+23,bottom-padding),radius=2,fill=accent)
    if role!='body':
        marker_style=block.get('marker_style','circle')
        if marker_style not in MARKER_STYLES:raise ValueError('Unsupported answer badge')
        marker=(x+15 if style=='split_panel' else x+20,
                y+(block['height']-52)/2,
                x+67 if style=='split_panel' else x+72,
                y+(block['height']+52)/2)
        badge_fill=paper if style in ('overlay_dark','split_panel') else accent
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
    plan=plan or default_plan(card)
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
    if window:heading_colour,heading_contrast,heading_shading=ink,contrast(ink,paper),0
    else:
        heading_colour,heading_contrast,heading_shading=protect_text(image,(64,155),title_rows,title_face,[paper,ink],3)
    example_contrast=None;example_shading=0;example_colour=None
    # Apply photographic shading before drawing any panels or heading glyphs,
    # so a nearby example's fade cannot wash out an already-rendered panel.
    for block in blocks:
        if block['style'] in ('italic_photo','italic_photo_fade','caption'):
            x,y=block['x'],block['y'];label_face=font(21,'SemiBold')
            example_y=y if block['style']=='caption' else y+measure(['PRIMJER'],label_face)[0]+16
            limit=photo_bounds or [0,header_end+14,WIDTH,1170]
            example_colour,example_contrast,example_shading=protect_text(
                image,(x,example_y),block['rows'],block['face'],[paper,ink],4.5,limit,
                extra=[] if block['style']=='caption' else [((x,y),['PRIMJER'],label_face)],
                line_spacing=block['line_spacing'],allow_fade=block['style']!='italic_photo')
            block['photo_colour']=example_colour;block['photo_contrast']=example_contrast
            block['photo_shading']=example_shading
            if block['role']!='example':example_contrast=None;example_shading=0
    # Another block's preset fade must not invalidate already-chosen glyph
    # colours. Validate the final photographic surface before drawing anything.
    if not window:
        protect_text(image,(64,155),title_rows,title_face,[heading_colour],3,allow_fade=False)
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
    if plan['design']=='editorial':
        # Approved editorial header; category and title retain their fixed anchors.
        label_face=font(22,'SemiBold');cursor=64
        for letter in label:
            draw.text((cursor,82),letter,font=label_face,fill=ink,anchor='lt')
            cursor+=label_face.getlength(letter)+4
        draw.line((64,120,270,120),fill=accent,width=3)
    else:
        label_face=font(27,'SemiBold')
        label_box=(64,64,64+round(label_face.getlength(label))+46,126)
        draw.rounded_rectangle(label_box,radius=16,fill=accent);centered(draw,label_box,label,label_face,ink)
    draw_rows(draw,(64,155),title_rows,title_face,heading_colour)
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
        elif style in ('plain','caption'):
            colour=block.get('photo_colour',ink)
            draw_rows(draw,(x,y),rows,face,colour,leading)
            if style=='caption':
                rule_y=y+measure(rows,face,leading)[0]+12
                draw.line((x,rule_y,x+min(160,block['width']),rule_y),fill=colour,width=3)
        else:
            colour=draw_panel(image,block,palette)
            draw=ImageDraw.Draw(image)
            text_y=y+padding if role=='body' else y+(block['height']-measure(rows,face,leading)[0])/2
            text_x=x+block['text_inset']
            if style=='overlay_light':
                # Glyph-level verification against the actual composited photograph;
                # do not silently add another preset/opacity to repair the proposal.
                protect_text(image,(text_x,text_y),rows,face,[colour],4.5,
                             line_spacing=leading,allow_fade=False)
            draw_rows(draw,(text_x,text_y),rows,face,colour,leading)
    with Image.open(ROOT/'assets/watermark.png') as source:
        if source.mode!='RGBA' or source.getextrema()[3][0]!=0 or source.getextrema()[3][1]==0:
            raise ValueError('Original logo must retain alpha transparency')
        logo=source.crop(source.getchannel('A').getbbox());logo.thumbnail((112,92),Image.Resampling.LANCZOS)
    image.alpha_composite(logo,(WIDTH-64-logo.width,HEIGHT-64-logo.height))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(output,'JPEG',quality=94,subsampling=0,optimize=True)
    return {'size':[WIDTH,HEIGHT],
            **({'treatment':'B','question_bounds':[64,155,1016,header_end],
                'photo_size':[photo_bounds[2]-photo_bounds[0],photo_bounds[3]-photo_bounds[1]]} if card.get('quiz_format')=='visual_identification' else {}),
            'typography':'hybrid','palette':palette_id,'panel_position':'free' if plan['confidence']=='high' else 'normal',
            'composition':plan,'design':plan['design'],'block_styles':{b['role']:b['style'] for b in blocks},'body_font_size':next((b['size'] for b in blocks if b['role']!='example'),density(card)[0]),
            'answer_badges':{b['role']:b.get('marker_style','circle') for b in blocks if b['role'] not in ('body','example')},
            'block_typography':{b['role']:{k:b[k] for k in ('font_size','line_spacing','max_lines','wrapping')} for b in blocks},'heading_font':'Lora SemiBold','body_font':'Inter',
            'example_style':next(({'italic_photo':'Lora Italic over photograph','italic_photo_fade':'Lora Italic over photograph with neutral fade','italic_footer':'Lora Italic on paper footer'}[b['style']] for b in blocks if b['role']=='example'),None),
            'panel_bounds':[list(map(round,b['bounds'])) for b in blocks if b['style'] in PANEL_STYLES],
            'example_bounds':next((list(map(round,b['bounds'])) for b in blocks if b['role']=='example'),None),
            'photo_bounds':photo_bounds,'photo_cropped':not bool(window) or window['fit']=='cover',
            'body_contrast':round(body_contrast,2),'heading_contrast':round(heading_contrast,2),
            'example_contrast':round(example_contrast,2) if example_contrast else None,
            'heading_shading':heading_shading,'example_shading':example_shading}
