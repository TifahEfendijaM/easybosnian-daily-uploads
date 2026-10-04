from functools import lru_cache

from PIL import ImageFont

from .core import ROOT
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
