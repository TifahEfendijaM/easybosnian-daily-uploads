"""Trusted declarative catalogue. Every treatment has a real Pillow renderer."""
DESIGNS = ('hybrid', 'editorial')
BODY_STYLES = ('rounded', 'outlined', 'plain', 'overlay_dark', 'overlay_light',
               'side_rule', 'caption', 'bottom_sheet', 'split_panel', 'minimal_rule')
EXAMPLE_STYLES = ('italic_photo', 'italic_photo_fade', 'italic_footer')
PANEL_STYLES = tuple(s for s in BODY_STYLES if s not in ('plain', 'caption'))
FONT_RANGES = {'body': (32, 48), 'answer': (32, 46), 'example': (28, 40)}
LEADING_RANGE = (1.20, 1.55)  # multiplier of the actual loaded face's point size
WRAPPING = ('balanced', 'natural')
STYLE_CATALOGUE = {
    'hybrid': 'Photographic background or complete contained photo; rounded accent badge and fixed Lora title. Body styles except plain; photo examples italic_photo or italic_photo_fade.',
    'editorial': 'Lesson/word paper page; tracked category underline and fixed Lora title. Plain explanation above a wide cover photo, italic_footer below. No other styles.',
    'rounded': 'Opaque paper panel, 24px rounded corners, inset accent rule; circular quiz marker.',
    'outlined': 'Opaque square paper panel with 3px accent outline; inset rule and square outlined quiz marker.',
    'plain': 'Unboxed Inter body on editorial paper only; no background, rule or border. Not valid for answers.',
    'overlay_dark': 'Opaque approved ink panel with paper text and rectangular paper answer marker. No custom colours or alpha.',
    'overlay_light': 'Approved paper translucent panel (fixed alpha 235), square corners, accent underline. Actual glyph contrast must pass after compositing.',
    'side_rule': 'Square paper panel with full-height 12px left accent bar; unboxed answer label.',
    'caption': 'Unboxed Inter SemiBold body directly on photograph with a contrast-safe separator and preset neutral contrast fade. Full-background body only, at most three lines.',
    'bottom_sheet': 'Wide paper sheet with 54px rounded top corners and square bottom; centered accent handle. Must start at y700 or lower and be at least 660px wide.',
    'split_panel': 'Square paper panel with a full-height 82px accent rail; answer label in rail, body text in its own column.',
    'minimal_rule': 'Square paper panel with just a 5px bottom accent rule; small inline answer label.',
    'italic_photo': 'Unboxed approved Lora Italic example and PRIMJER label directly on photograph. No fade: reject if actual glyph contrast fails.',
    'italic_photo_fade': 'Unboxed approved Lora Italic example and label over photograph, using only renderer-owned neutral feathered contrast presets when needed.',
    'italic_footer': 'Unboxed approved Lora Italic example on editorial paper footer below photo, small PRIMJER label and thin separator. No example box.',
}


def role_type(role):
    return role if role in ('body', 'example') else 'answer'


def typography(role, size, leading, max_lines=None, wrapping='balanced'):
    low, high = FONT_RANGES[role_type(role)]
    if type(size) is not int or not low <= size <= high:
        raise ValueError('Font size outside the approved role range')
    if type(leading) not in (int, float) or not LEADING_RANGE[0] <= leading <= LEADING_RANGE[1]:
        raise ValueError('Line spacing outside the approved multiplier range')
    if max_lines is not None and (type(max_lines) is not int or not 1 <= max_lines <= 12):
        raise ValueError('Invalid maximum line count')
    if wrapping not in WRAPPING:raise ValueError('Unsupported wrapping preference')
