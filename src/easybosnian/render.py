import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .core import ROOT, LAYOUTS
from .validate import instructional

WIDTH, HEIGHT, MARGIN = 1080, 1350, 64
LABELS = {"quiz": "PITANJE DANA", "lesson": "ZNAŠ LI?", "word": "RIJEČ DANA"}


def font(size, weight="Regular"):
    return ImageFont.truetype(str(ROOT / "assets/fonts" / f"Inter-{weight}.ttf"), size)


def wrap(text, face, width):
    rows, row = [], ""
    for token in text.split(" "):
        candidate = (row + " " + token).strip()
        if face.getlength(candidate) <= width:
            row = candidate
        else:
            if row:
                rows.append(row)
            if face.getlength(token) > width:
                raise ValueError("An unbreakable word exceeds the available width")
            row = token
    if row:
        rows.append(row)
    if " ".join(rows) != text:
        raise ValueError("Wrapping would alter exact reviewed text")
    return rows


def measure(rows, face):
    ascent, descent = face.getmetrics()
    step = round((ascent + descent) * 1.16)
    glyph_height = max(face.getbbox(row)[3] - face.getbbox(row)[1] for row in rows)
    return glyph_height + (len(rows) - 1) * step, step


def luminance(colour):
    if isinstance(colour, str): colour = tuple(int(colour[i:i+2],16) for i in (1,3,5))
    channels = [v/255 for v in colour[:3]]
    linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def aligned_x(x, width, row, face, align):
    extent = face.getlength(row)
    return x + (width - extent) * ({'left':0, 'center':.5, 'right':1}[align])


def protect_heading(image, xy, rows, face, palette, width, align):
    h, _ = measure(rows, face)
    x, y = map(int, xy)
    box = (x, y, x + width, y + h + 4)
    mask = Image.new('L', (width, h + 4))
    draw_aligned(ImageDraw.Draw(mask), (0, 0), rows, face, 255, width, align)
    points = [(px, py) for py in range(0, mask.height, 3) for px in range(0, mask.width, 3) if mask.getpixel((px, py)) > 128]
    region = image.crop(box)
    rgb = tuple(int(palette['scrim'][i:i+2], 16) for i in (1, 3, 5))
    for alpha in (0, 50, 90, 130, 170, 210, 255):
        candidate = Image.alpha_composite(region, Image.new('RGBA', region.size, (*rgb, alpha))) if alpha else region
        lowest = min((contrast(palette['panel'], candidate.getpixel(p)) for p in points), default=10)
        if lowest >= 3:
            if alpha: image.paste(candidate, box[:2])
            return lowest
    raise ValueError('Heading contrast fails on actual artwork; rewrite rather than hide text')


def draw_aligned(draw, xy, rows, face, fill, width, align):
    height, step = measure(rows, face)
    for i, row in enumerate(rows):
        draw_rows(draw, (aligned_x(xy[0], width, row, face, align), xy[1]+i*step), [row], face, fill)
    return height


def draw_rows(draw, xy, rows, face, fill):
    height, step = measure(rows, face)
    x, y = xy
    for i, row in enumerate(rows):
        box = draw.textbbox((0, 0), row, font=face)
        draw.text((x - box[0], y + i * step - box[1]), row, font=face, fill=fill)
    return height


def centered(draw, box, text, face, fill):
    bounds = draw.textbbox((0, 0), text, font=face)
    x = (box[0] + box[2] - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = (box[1] + box[3] - (bounds[3] - bounds[1])) / 2 - bounds[1]
    draw.text((x, y), text, font=face, fill=fill)


def density(card):
    length = len(" ".join(instructional(card)))
    return (44, 38) if length <= 160 else ((38, 30) if length <= 240 else (34, 24))


def panel(draw, box, style, palette, option=False):
    ink, accent, paper = palette["ink"], palette["accent"], palette["panel"]
    x, y, r, b = box
    if style == "rounded":
        draw.rounded_rectangle(box, radius=38 if not option else (b - y) // 2, fill=paper)
    else:
        draw.rounded_rectangle(box, radius=18, fill=accent if style == "poster" and option else paper)
    if style == "editorial":
        draw.rectangle((x, y, x + 5, b), fill=accent)
    elif style == "framed":
        draw.rectangle(box, outline=accent, width=3)
        draw.rectangle((x + 8, y + 8, r - 8, b - 8), outline=ink, width=1)
    elif style == "notebook":
        draw.line((x + 20, y + 10, x + 20, b - 10), fill=accent, width=3)
        for ry in range(round(y + 20), round(b), 15):
            draw.line((x + 2, ry, x + 13, ry), fill=accent, width=1)
    elif style == "ribbon":
        draw.rectangle((x, y, r, y + 7), fill=accent)
    elif style == "split-cards":
        draw.rectangle((r - 8, y, r, b), fill=accent)
    elif style == "minimal":
        draw.line((x, b, r, b), fill=accent, width=2)
    elif style == "poster":
        draw.rectangle((x, y, x + 10, b), fill=ink)


def render(card, palette_id, background, output):
    palette = json.loads((ROOT / 'data/design-palettes.json').read_text())[palette_id]
    style = card['design_template']
    if style not in LAYOUTS: raise ValueError('Unapproved layout')
    layout = json.loads((ROOT / 'data/design-layouts.json').read_text())[style]
    body_contrast = min(contrast(palette['ink'], palette['panel']), contrast(palette['ink'], palette['accent']))
    if body_contrast < 4.5: raise ValueError('Approved palette no longer meets text contrast requirements')
    if len(' '.join(instructional(card))) > 460: raise ValueError('Copy exceeds the instructional maximum; rewrite')
    x, width = layout['x'], layout['width']
    body_size, padding = density(card); body_face = font(body_size)
    face_label = font(24 if style == 'poster' else 27, 'SemiBold')
    label = LABELS[card['kind']]; label_width = round(face_label.getlength(label)) + 46
    title = card['question'] if card['kind'] == 'quiz' else card['heading']
    title_size = layout['quiz_size'] if card['kind'] == 'quiz' else layout['title_size']
    title_face = font(title_size, 'Bold' if style == 'poster' else 'SemiBold')
    title_rows = wrap(title, title_face, width)
    # Narrow columns use their approved smaller heading size; never truncate.
    if len(title_rows) > (3 if card['kind'] == 'quiz' else 2):
        raise ValueError('Heading exceeds the selected layout; rewrite or choose a wider layout')
    title_height, _ = measure(title_rows, title_face)
    heading_height = 62 + layout['gap'] + title_height
    blocks = []; y = 0
    if card['kind'] == 'quiz':
        for option in card['options']:
            rows = wrap(option['text'], body_face, width-142)
            text_height, _ = measure(rows, body_face)
            block_height = max(92, text_height + 2*padding)
            blocks.append((y, block_height, rows, option['label'], False)); y += block_height + 16
    else:
        for text, example in [(card['body'], False)] + ([(card['example'], True)] if card.get('example') else []):
            rows = wrap(text, body_face, width-2*padding-24)
            text_height, _ = measure(rows, body_face)
            label_height = measure(['PRIMJER'], font(22, 'SemiBold'))[0]+16 if example else 0
            block_height = text_height + 2*padding + label_height
            blocks.append((y, block_height, rows, None, example)); y += block_height + (22 if style == 'split-cards' else 14)
    blocks_height = y - (16 if card['kind'] == 'quiz' else 22 if style == 'split-cards' else 14)
    total_height = heading_height + 28 + blocks_height
    anchor = layout['anchor']; bottom = 1170
    if anchor == 'split':
        heading_top = 64; panel_top = bottom-blocks_height
        if panel_top < heading_top+heading_height+80:
            raise ValueError('Split layout needs a visible middle scene; choose another layout or rewrite')
    else:
        heading_top = 64 if anchor == 'top' else bottom-total_height if anchor == 'bottom' else round((bottom+64-total_height)/2)
        panel_top = heading_top+heading_height+28
    if heading_top < 64 or panel_top+blocks_height > bottom:
        raise ValueError('Copy does not fit the chosen layout; rewrite without truncation')
    panel_area = sum(b[1]*width for b in blocks)
    if panel_area > WIDTH*HEIGHT*.49:
        raise ValueError('Copy panels would obscure too much artwork; rewrite')
    image = ImageOps.fit(Image.open(background).convert('RGB'), (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS).convert('RGBA')
    ink, accent, paper = palette['ink'], palette['accent'], palette['panel']
    title_y = heading_top+62+layout['gap']
    heading_contrast = protect_heading(image, (x,title_y), title_rows, title_face, palette, width, layout['align'])
    draw = ImageDraw.Draw(image)
    label_x = x + (width-label_width)*({'left':0, 'center':.5, 'right':1}[layout['label_align']])
    label_box = (label_x, heading_top, label_x+label_width, heading_top+62)
    # Opaque category badge keeps all three category labels readable anywhere.
    if style == 'rounded': draw.rounded_rectangle(label_box, radius=31, fill=accent)
    elif style in ('framed','minimal'):
        draw.rounded_rectangle(label_box, radius=12, fill=paper)
        if style == 'framed': draw.rounded_rectangle(label_box, radius=12, outline=accent, width=3)
        else: draw.line((label_box[0], label_box[3], label_box[2], label_box[3]), fill=accent, width=3)
    else:
        draw.rounded_rectangle(label_box, radius=8, fill=accent)
        if style == 'ribbon': draw.polygon([(label_x,heading_top+62),(label_x+15,heading_top+78),(label_x+15,heading_top+62)],fill=ink)
    centered(draw,label_box,label,face_label,ink)
    draw_aligned(draw,(x,title_y),title_rows,title_face,paper,width,layout['align'])
    bounds=[]
    for offset, block_height, rows, marker, example in blocks:
        top=panel_top+offset; box=(x,top,x+width,top+block_height)
        panel(draw,box,style,palette,option=marker is not None)
        if marker:
            marker_box=(x+22,top+(block_height-52)/2,x+74,top+(block_height+52)/2)
            if style=='rounded': draw.ellipse(marker_box,fill=accent)
            else: draw.rectangle(marker_box,fill=ink if style=='poster' else accent)
            centered(draw,marker_box,marker,font(28,'Bold'),paper if style=='poster' else ink)
            text_height,_=measure(rows,body_face)
            draw_rows(draw,(x+110,top+(block_height-text_height)/2),rows,body_face,ink)
        else:
            draw.rounded_rectangle((x+18,top+padding,x+23,top+block_height-padding),radius=2,fill=accent)
            text_x,text_y=x+padding+24,top+padding
            if example: text_y+=draw_rows(draw,(text_x,text_y),['PRIMJER'],font(22,'SemiBold'),ink)+16
            draw_rows(draw,(text_x,text_y),rows,body_face,ink)
        bounds.append([round(v) for v in box])
    logo=Image.open(ROOT/'assets/watermark.png')
    if logo.mode!='RGBA' or logo.getextrema()[3][0]!=0 or logo.getextrema()[3][1]==0: raise ValueError('Original logo must retain full alpha transparency')
    logo=logo.crop(logo.getchannel('A').getbbox());logo.thumbnail((112,92),Image.Resampling.LANCZOS)
    image.alpha_composite(logo,(WIDTH-MARGIN-logo.width,HEIGHT-MARGIN-logo.height))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(output,'JPEG',quality=94,subsampling=0,optimize=True)
    return {'size':[WIDTH,HEIGHT],'body_font_size':body_size,'panel_padding':padding,'panel_bounds':bounds,
            'heading_bounds':[x,title_y,x+width,title_y+title_height], 'label_bounds':list(label_box),
            'heading_alignment':layout['align'],'heading_font_size':title_size,'scene_focus':layout['scene_focus'],
            'example_label':'PRIMJER' if card.get('example') else None,'inset_accent_line':card['kind']!='quiz',
            'panel_area_ratio':round(panel_area/(WIDTH*HEIGHT),3),'body_contrast':round(body_contrast,2),'heading_contrast':round(heading_contrast,2)}
