import json
from pathlib import Path
from functools import lru_cache

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
    # Keep the minimum line count but distribute words across those lines.
    # This avoids an almost-full paragraph followed by a tiny orphan line.
    if len(rows) > 1:
        words = text.split(" ")
        @lru_cache(None)
        def balanced(start, remaining):
            if remaining == 0:
                return (0, ()) if start == len(words) else (float('inf'), ())
            best = (float('inf'), ())
            for end in range(start + 1, len(words) - remaining + 2):
                line = " ".join(words[start:end])
                length = face.getlength(line)
                if length > width: break
                tail_cost, tail = balanced(end, remaining - 1)
                slack = (width - length) / width
                cost = slack * slack * (0.65 if remaining == 1 else 1)
                if remaining == 1 and length < width * 0.35: cost += 1
                if len(words[end - 1]) <= 2 and remaining > 1: cost += 0.04
                candidate = (cost + tail_cost, (line, *tail))
                if candidate[0] < best[0]: best = candidate
            return best
        cost, chosen = balanced(0, len(rows))
        if chosen: rows = list(chosen)
    if " ".join(rows) != text:
        raise ValueError("Wrapping would alter exact reviewed text")
    return rows


def measure(rows, face):
    ascent, descent = face.getmetrics()
    boxes = [face.getbbox(row) for row in rows]
    glyph_height = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    step = max(round(face.size * 1.30), glyph_height + 6)
    return glyph_height + (len(rows) - 1) * step, step


def luminance(colour):
    if isinstance(colour, str): colour = tuple(int(colour[i:i+2],16) for i in (1,3,5))
    channels = [v/255 for v in colour[:3]]
    linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def protect_heading(image, xy, rows, face, palette):
    # Check the actual pixels under real glyphs, adding a local scrim only if needed.
    h,_=measure(rows,face)
    box=(MARGIN,int(xy[1]),WIDTH-MARGIN,int(xy[1]+h+3))
    mask=Image.new('L',(box[2]-box[0],box[3]-box[1]))
    draw_rows(ImageDraw.Draw(mask),(0,0),rows,face,255)
    points=[(x,y) for y in range(0,mask.height,3) for x in range(0,mask.width,3) if mask.getpixel((x,y))>128]
    region=image.crop(box)
    for alpha in (0,50,90,130,170,210):
        rgb=tuple(int(palette['scrim'][i:i+2],16) for i in (1,3,5))
        candidate=Image.alpha_composite(region,Image.new('RGBA',region.size,(*rgb,alpha))) if alpha else region
        lowest=min((contrast(palette['panel'],candidate.getpixel(p)) for p in points),default=10)
        if lowest>=3:
            if alpha: image.paste(candidate,box[:2])
            return lowest
    raise ValueError('Heading contrast fails on the actual artwork; reject rather than hide text')


def draw_rows(draw, xy, rows, face, fill):
    height, step = measure(rows, face)
    x, y = xy
    # All lines share a baseline origin; per-line top alignment shifts rows
    # containing accents/descenders and creates visibly uneven paragraph spacing.
    top = min(face.getbbox(row)[1] for row in rows)
    for i, row in enumerate(rows):
        box = draw.textbbox((0, 0), row, font=face)
        draw.text((x - box[0], y + i * step - top), row, font=face, fill=fill)
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
    palette = json.loads((ROOT / "data/design-palettes.json").read_text())[palette_id]
    minimum_body_contrast=min(contrast(palette['ink'],palette['panel']),contrast(palette['ink'],palette['accent']))
    if minimum_body_contrast<4.5: raise ValueError('Approved palette no longer meets text contrast requirements')
    style = card["design_template"]
    if style not in LAYOUTS:
        raise ValueError("Unapproved layout")
    height = HEIGHT
    image = ImageOps.fit(Image.open(background).convert("RGB"), (WIDTH, height), method=Image.Resampling.LANCZOS).convert("RGBA")
    # Palette-matched gradient protects headings while leaving lower artwork visible.
    overlay = Image.new("RGBA", image.size)
    od = ImageDraw.Draw(overlay)
    scrim = tuple(int(palette["scrim"][i:i + 2], 16) for i in (1, 3, 5))
    for y in range(height):
        alpha = round(205 * max(0, 1 - y / 850))
        od.line((0, y, WIDTH, y), fill=(*scrim, alpha))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)
    ink, accent, paper = palette["ink"], palette["accent"], palette["panel"]
    face_label = font(27, "SemiBold")
    label = LABELS[card["kind"]]
    label_width = round(face_label.getlength(label)) + 46
    label_box = (MARGIN, MARGIN, MARGIN + label_width, MARGIN + 62)
    if style == "rounded":
        draw.rounded_rectangle(label_box, radius=31, fill=accent)
    elif style == "framed":
        draw.rectangle(label_box, outline=paper, width=2)
    elif style == "minimal":
        draw.line((label_box[0], label_box[3], label_box[2], label_box[3]), fill=accent, width=3)
    else:
        draw.rectangle(label_box, fill=accent)
        if style == "notebook":
            draw.polygon([(label_box[2], MARGIN), (label_box[2] + 18, MARGIN + 31), (label_box[2], MARGIN + 62)], fill=accent)
        elif style == "ribbon":
            draw.polygon([(MARGIN, MARGIN + 62), (MARGIN + 15, MARGIN + 80), (MARGIN + 15, MARGIN + 62)], fill=ink)
    centered(draw, label_box, label, face_label, paper if style in ("framed", "minimal") else ink)
    y = MARGIN + 62 + (29 if style != "ribbon" else 36)
    body_size, padding = density(card)
    body_face = font(body_size)
    full_width = WIDTH - 2 * MARGIN
    blocks = []
    if card["kind"] == "quiz":
        title_face = font(52 if style != "poster" else 58, "SemiBold")
        question_rows = wrap(card["question"], title_face, full_width)
        if len(question_rows) > 3:
            raise ValueError("Quiz question exceeds three lines; rewrite")
        question_height, _ = measure(question_rows, title_face)
        heading_contrast=protect_heading(image,(MARGIN,y),question_rows,title_face,palette)
        draw=ImageDraw.Draw(image)
        draw_rows(draw, (MARGIN, y), question_rows, title_face, paper)
        y += question_height + 28
        for option in card["options"]:
            rows = wrap(option["text"], body_face, full_width - 142)
            text_height, _ = measure(rows, body_face)
            box_height = max(92, text_height + 2 * padding)
            blocks.append((y, box_height, rows, option["label"], False))
            y += box_height + 16
    else:
        title_face = font(74 if style != "poster" else 80, "SemiBold")
        rows = wrap(card["heading"], title_face, full_width)
        if len(rows) > 2:
            raise ValueError("Heading too long; rewrite")
        title_height, _ = measure(rows, title_face)
        heading_contrast=protect_heading(image,(MARGIN,y),rows,title_face,palette)
        draw=ImageDraw.Draw(image)
        draw_rows(draw, (MARGIN, y), rows, title_face, paper)
        y += title_height + 28
        groups = [(card["body"], False)] + ([(card["example"], True)] if card.get("example") else [])
        for text, is_example in groups:
            rows = wrap(text, body_face, full_width - 2 * padding - 24)
            text_height, _ = measure(rows, body_face)
            # Measure the separate template label too, rather than overlapping the example.
            example_label_height = measure(["PRIMJER"], font(22, "SemiBold"))[0] + 16 if is_example else 0
            box_height = text_height + 2 * padding + example_label_height
            blocks.append((y, box_height, rows, None, is_example))
            y += box_height + (22 if style == "split-cards" else 14)
    panel_area = sum(b[1] * full_width for b in blocks)
    if y > min(height - 180, 1050) or panel_area > WIDTH * height * 0.49:
        raise ValueError("Copy does not fit while preserving artwork; rewrite reviewed package")
    bounds = []
    for index, (top, block_height, rows, marker, is_example) in enumerate(blocks):
        box = (MARGIN, top, WIDTH - MARGIN, top + block_height)
        panel(draw, box, style, palette, option=marker is not None)
        if marker:
            marker_box = (MARGIN + 22, top + (block_height - 52) / 2, MARGIN + 74, top + (block_height + 52) / 2)
            if style == "rounded":
                draw.ellipse(marker_box, fill=accent)
            else:
                draw.rectangle(marker_box, fill=accent if style != "poster" else ink)
            centered(draw, marker_box, marker, font(28, "Bold"), paper if style == "poster" else ink)
            text_height, _ = measure(rows, body_face)
            draw_rows(draw, (MARGIN + 110, top + (block_height - text_height) / 2), rows, body_face, ink)
        else:
            # A quiet inset accent line ties the definition and example panels together.
            draw.rounded_rectangle((MARGIN + 18, top + padding, MARGIN + 23, top + block_height - padding), radius=2, fill=accent)
            text_x, text_y = MARGIN + padding + 24, top + padding
            if is_example:
                label_face = font(22, "SemiBold")
                text_y += draw_rows(draw, (text_x, text_y), ["PRIMJER"], label_face, ink) + 16
            draw_rows(draw, (text_x, text_y), rows, body_face, ink)
        bounds.append([round(x) for x in box])
    logo = Image.open(ROOT / "assets/watermark.png")
    if logo.mode != "RGBA" or logo.getextrema()[3][0] != 0 or logo.getextrema()[3][1] == 0:
        raise ValueError("Original logo must retain full alpha transparency")
    bbox = logo.getchannel("A").getbbox()
    logo = logo.crop(bbox)
    logo.thumbnail((112, 92), Image.Resampling.LANCZOS)
    image.alpha_composite(logo, (WIDTH - MARGIN - logo.width, height - MARGIN - logo.height))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, "JPEG", quality=94, subsampling=0, optimize=True)
    return {"size": [WIDTH, height], "body_font_size": body_size, "panel_padding": padding, "panel_bounds": bounds, "example_label": "PRIMJER" if card.get("example") else None, "inset_accent_line": card["kind"] != "quiz", "paragraph_alignment":"left", "balanced_wrapping":True, "body_line_step":measure(["ČćŠšŽžĐđ"],body_face)[1], "panel_area_ratio": round(panel_area / (WIDTH * height), 3), "body_contrast":round(minimum_body_contrast,2),"heading_contrast":round(heading_contrast,2)}
