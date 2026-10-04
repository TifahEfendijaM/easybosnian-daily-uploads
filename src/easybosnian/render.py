from functools import lru_cache

from PIL import ImageFont

from .core import ROOT
from .validate import instructional

WIDTH, HEIGHT, MARGIN = 1080, 1350, 64
LABELS = {"quiz": "PITANJE DANA", "lesson": "ZNAŠ LI?", "word": "RIJEČ DANA"}


def font(size, weight="Regular"):
    return ImageFont.truetype(str(ROOT / "assets/fonts" / f"Inter-{weight}.ttf"), size)


class WrappedRows(list):
    """Exact source and invisible wrap separators; never replacement model copy."""
    def __init__(self, rows, source, separators):
        super().__init__(rows); self.source=source; self.separators=separators

    def reconstructed(self):
        return ''.join(row + (self.separators[i] if i<len(self.separators) else '')
                       for i,row in enumerate(self))


def wrap(text, face, width, preference='balanced'):
    import re
    if preference not in ('balanced','natural') or not text or width <= 0:
        raise ValueError('Unsupported wrapping input')
    # Break at ordinary Unicode spaces, but keep NBSP/narrow NBSP/word joiners
    # with their words. Newlines/control instructions are not approved text.
    if any(c in text for c in ('\n','\r','\t')):
        raise ValueError('Manual line breaks/control whitespace are unsupported')
    parts=re.split(r'([ \u1680\u2000-\u200a\u205f\u3000]+)', text)
    words=parts[::2]; gaps=parts[1::2]
    if any(not word for word in words):raise ValueError('Leading/trailing whitespace cannot be removed without truncation')
    def line(start,end):
        return ''.join(words[i]+(gaps[i] if i<end-1 else '') for i in range(start,end))
    def length(value):
        box=face.getbbox(value)
        return max(face.getlength(value),box[2]-box[0])
    rows=[]; breaks=[]; start=0
    for end in range(1,len(words)+1):
        if length(line(start,end))>width:
            if end-1==start:raise ValueError('An unbreakable word exceeds the available width')
            rows.append(line(start,end-1)); breaks.append(end-1); start=end-1
            if length(words[start])>width:raise ValueError('An unbreakable word exceeds the available width')
    rows.append(line(start,len(words)))
    if len(rows)>1 and preference=='balanced':
        @lru_cache(None)
        def balanced(start,remaining):
            if remaining==0:return (0,()) if start==len(words) else (float('inf'),())
            best=(float('inf'),())
            for end in range(start+1,len(words)-remaining+2):
                line_length=length(line(start,end))
                if line_length>width:break
                cost,tail=balanced(end,remaining-1)
                slack=(width-line_length)/width
                cost+=slack*slack*(.65 if remaining==1 else 1)
                if remaining==1 and line_length<width*.35:cost+=1
                if len(words[end-1])<=2 and remaining>1:cost+=.04
                if cost<best[0]:best=(cost,(end,*tail))
            return best
        _, ends=balanced(0,len(rows))
        if ends:
            rows=[];start=0
            for end in ends:rows.append(line(start,end));start=end
            breaks=list(ends[:-1])
    result=WrappedRows(rows,text,[gaps[end-1] for end in breaks])
    if result.reconstructed()!=text:raise ValueError('Wrapping would alter exact reviewed text')
    return result


def measure(rows, face, line_spacing=None):
    if not rows:raise ValueError('Cannot measure empty copy')
    boxes=[face.getbbox(row) for row in rows]
    glyph_height=max(b[3] for b in boxes)-min(b[1] for b in boxes)
    if line_spacing is None:step=max(round(face.size*1.30),glyph_height+6)
    else:
        step=round(face.size*line_spacing)
        if step<glyph_height+4:raise ValueError('Requested leading collides with measured glyphs')
    return glyph_height+(len(rows)-1)*step,step


def luminance(colour):
    if isinstance(colour, str): colour = tuple(int(colour[i:i+2],16) for i in (1,3,5))
    channels = [v/255 for v in colour[:3]]
    linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def draw_rows(draw, xy, rows, face, fill, line_spacing=None):
    height, step = measure(rows, face, line_spacing)
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
