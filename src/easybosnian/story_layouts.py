"""Separate photo/text treatment B, using reviewed copy and original artwork."""
from PIL import Image, ImageDraw, ImageOps

from .core import ROOT
from .render import LABELS, centered, contrast, density, draw_rows, font, measure, wrap


def tall_story_image(card, background, destination, palette):
    if card['kind'] == 'quiz' and card.get('quiz_format') == 'visual_identification':
        return visual_quiz_image(card, background, destination, palette)
    if card['kind'] not in ('lesson', 'word'):
        raise ValueError('Tall Story treatment is only for lesson and word cards')
    if not background:
        raise ValueError('Tall Stories require the original photographic background')
    ink, accent, paper = palette['ink'], palette['accent'], palette['panel']
    if min(contrast(ink, paper), contrast(ink, accent), contrast(ink, '#ffffff')) < 4.5:
        raise ValueError('Tall Story text contrast fails; reject rather than alter text')
    image = Image.new('RGBA', (1080, 1920), paper)
    draw = ImageDraw.Draw(image)
    label_face = font(27, 'SemiBold'); label = LABELS[card['kind']]
    label_box = (64, 180, 64 + round(label_face.getlength(label)) + 48, 242)
    draw.rounded_rectangle(label_box, radius=16, fill=accent)
    centered(draw, label_box, label, label_face, ink)
    title_face = font(80, 'SemiBold')
    title_rows = wrap(card['heading'], title_face, 952)
    if len(title_rows) > 2:
        raise ValueError('Tall Story heading exceeds two lines; reject without truncation')
    title_height = draw_rows(draw, (64, 278), title_rows, title_face, ink)
    photo_top = 278 + title_height + 34
    body_size, padding = density(card); body_face = font(body_size)
    groups = [(card['body'], False)]
    if card.get('example'): groups.append((card['example'], True))
    blocks = []
    for text, example in groups:
        rows = wrap(text, body_face, 952 - 2 * padding - 24)
        text_height, _ = measure(rows, body_face)
        label_height = measure(['PRIMJER'], font(22, 'SemiBold'))[0] + 16 if example else 0
        blocks.append((rows, example, text_height + 2 * padding + label_height))
    text_height = sum(height for _, _, height in blocks) + 20 * (len(blocks) - 1)
    photo_height = min(730, 1650 - photo_top - 34 - text_height)
    if photo_height < 360:
        raise ValueError('Tall Story copy does not fit while preserving its photo; reject without truncation')
    with Image.open(background) as original:
        photo = ImageOps.contain(original.convert('RGB'), (952, int(photo_height)), Image.Resampling.LANCZOS)
    mask = Image.new('L', photo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, photo.width - 1, photo.height - 1), radius=30, fill=255)
    image.paste(photo, ((1080 - photo.width) // 2, int(photo_top)), mask)
    draw = ImageDraw.Draw(image); y = photo_top + photo.height + 34
    bounds = []
    for rows, example, height in blocks:
        box = (64, y, 1016, y + height)
        draw.rounded_rectangle(box, radius=24, fill='#ffffff')
        draw.rounded_rectangle((84, y + padding, 89, y + height - padding), radius=2, fill=accent)
        text_x, text_y = 64 + padding + 24, y + padding
        if example:
            text_y += draw_rows(draw, (text_x, text_y), ['PRIMJER'], font(22, 'SemiBold'), ink) + 16
        draw_rows(draw, (text_x, text_y), rows, body_face, ink)
        bounds.append([round(value) for value in box]); y += height + 20
    with Image.open(ROOT / 'assets/watermark.png') as original_logo:
        if original_logo.mode != 'RGBA' or original_logo.getextrema()[3][0] != 0 or original_logo.getextrema()[3][1] == 0:
            raise ValueError('Original Story logo must retain transparency')
        logo = original_logo.crop(original_logo.getchannel('A').getbbox())
        logo.thumbnail((102, 80), Image.Resampling.LANCZOS)
    image.alpha_composite(logo, (1016 - logo.width, 1690))
    image.convert('RGB').save(destination, 'JPEG', quality=94, subsampling=0, optimize=True)
    return {'treatment': 'B', 'size': [1080, 1920], 'body_font_size': body_size,
            'panel_bounds': bounds, 'photo_size': list(photo.size), 'photo_cropped': False}


def visual_quiz_image(card, background, destination, palette, height=1920):
    """The picture is the question; show the entire photo above question/choices."""
    if card['kind'] != 'quiz' or card.get('quiz_format') != 'visual_identification':
        raise ValueError('Separate quiz photo requires reviewed visual-identification metadata')
    if not background or height not in (1350, 1920):
        raise ValueError('Visual quiz requires its original photo and approved output dimensions')
    ink, accent, paper = palette['ink'], palette['accent'], palette['panel']
    body_contrast = min(contrast(ink, paper), contrast(ink, accent), contrast(ink, '#ffffff'))
    if body_contrast < 4.5: raise ValueError('Visual quiz text contrast fails')
    image = Image.new('RGBA', (1080, height), paper); draw = ImageDraw.Draw(image)
    top = 180 if height == 1920 else 64
    label_face = font(27, 'SemiBold'); label = LABELS['quiz']
    label_box = (64, top, 64 + round(label_face.getlength(label)) + 48, top + 62)
    draw.rounded_rectangle(label_box, radius=16, fill=accent)
    centered(draw, label_box, label, label_face, ink)
    question_face = font(52, 'SemiBold')
    question_rows = wrap(card['question'], question_face, 952)
    if len(question_rows) > 3: raise ValueError('Visual quiz question exceeds three measured lines')
    question_height, _ = measure(question_rows, question_face)
    body_size, padding = density(card); body_face = font(body_size)
    blocks = []
    for option in card['options']:
        rows = wrap(option['text'], body_face, 810)
        text_height, _ = measure(rows, body_face)
        blocks.append((option['label'], rows, max(88, text_height + 36)))
    options_height = sum(b[2] for b in blocks) + 14 * (len(blocks) - 1)
    photo_top = top + 62 + 28
    text_bottom = 1650 if height == 1920 else 1200
    photo_height = min(680 if height == 1920 else 510,
                       text_bottom - photo_top - 28 - question_height - 24 - options_height)
    if photo_height < (360 if height == 1920 else 240):
        raise ValueError('Visual quiz copy does not fit while preserving its photo; reject without truncation')
    with Image.open(background) as original:
        photo = ImageOps.contain(original.convert('RGB'), (952, int(photo_height)), Image.Resampling.LANCZOS)
    mask = Image.new('L', photo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, photo.width - 1, photo.height - 1), radius=30, fill=255)
    image.paste(photo, ((1080 - photo.width) // 2, int(photo_top)), mask)
    draw = ImageDraw.Draw(image); y = photo_top + photo.height + 28
    draw_rows(draw, (64, y), question_rows, question_face, ink)
    y += question_height + 24; bounds = []
    for label, rows, block_height in blocks:
        box = (64, y, 1016, y + block_height)
        draw.rounded_rectangle(box, radius=24, fill='#ffffff')
        marker = (86, y + (block_height - 52) / 2, 138, y + (block_height + 52) / 2)
        draw.ellipse(marker, fill=accent); centered(draw, marker, label, font(28, 'Bold'), ink)
        text_height, _ = measure(rows, body_face)
        draw_rows(draw, (174, y + (block_height - text_height) / 2), rows, body_face, ink)
        bounds.append([round(v) for v in box]); y += block_height + 14
    with Image.open(ROOT / 'assets/watermark.png') as original_logo:
        if original_logo.mode != 'RGBA' or original_logo.getextrema()[3][0] != 0 or original_logo.getextrema()[3][1] == 0:
            raise ValueError('Original quiz logo must retain transparency')
        logo = original_logo.crop(original_logo.getchannel('A').getbbox())
        logo.thumbnail((102, 80), Image.Resampling.LANCZOS)
    image.alpha_composite(logo, (1016 - logo.width, 1690 if height == 1920 else 1230))
    image.convert('RGB').save(destination, 'JPEG', quality=94, subsampling=0, optimize=True)
    return {'treatment': 'B', 'size': [1080, height], 'body_font_size': body_size,
            'panel_padding': padding, 'panel_bounds': bounds, 'photo_size': list(photo.size),
            'photo_cropped': False, 'body_contrast': round(body_contrast, 2),
            'heading_contrast': round(contrast(ink, paper), 2),
            'panel_area_ratio': round(sum(b[2] for b in blocks) * 952 / (1080 * height), 3)}
