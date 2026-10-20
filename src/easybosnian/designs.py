"""Trusted declarative catalogue. Every treatment has a real Pillow renderer."""
DESIGNS = ('hybrid', 'editorial')
BODY_STYLES = ('rounded', 'outlined', 'plain', 'overlay_dark', 'overlay_light',
               'side_rule', 'bottom_sheet', 'split_panel', 'minimal_rule',
               'double_frame', 'notebook_margin', 'top_ribbon', 'corner_brackets', 'soft_corner')
EXAMPLE_STYLES = ('italic_photo', 'italic_photo_fade', 'italic_footer')
PANEL_STYLES = tuple(s for s in BODY_STYLES if s != 'plain')
ANSWER_STYLES = (*PANEL_STYLES, 'pill', 'folded_corner')
PANEL_STYLES = (*PANEL_STYLES, 'pill', 'folded_corner')
CATEGORY_STYLES = ('rounded', 'pill', 'ribbon', 'underlined', 'outlined', 'tab')
PHOTO_TONES = ('auto', 'paper_dark', 'ink_light', 'paper_ink', 'ink_paper', 'accent_ink',
               'ink_accent', 'accent_dark', 'accent_light', 'paper_accent')
PANEL_TONES = ('auto', 'ink_paper', 'paper_ink', 'ink_accent', 'accent_ink')
FADE_STYLES = ('standard', 'soft')
PANEL_OPACITIES = {'solid': 255, 'soft': 230, 'translucent': 191}
FONT_RANGES = {'body': (32, 48), 'answer': (32, 46), 'example': (28, 40)}
MARKER_STYLES = ('circle', 'rounded_square', 'square', 'triangle')
LEADING_RANGE = (1.20, 1.55)  # multiplier of the actual loaded face's point size
WRAPPING = ('balanced', 'natural')
STYLE_CATALOGUE = {
    'hybrid': 'Photographic background or complete contained photo; approved category treatment and fixed Lora title. Body styles except plain; photo examples italic_photo or italic_photo_fade.',
    'editorial': 'Lesson/word paper page; approved category treatment and fixed Lora title. Plain explanation above a wide cover photo, italic_footer below. No other body styles.',
    'rounded': 'Paper panel, 24px rounded corners, inset accent rule; independently chosen approved quiz badge.',
    'outlined': 'Square paper panel with 3px accent outline; inset rule and independently chosen approved quiz badge.',
    'plain': 'Unboxed Inter body on editorial paper only; no background, rule or border. Not valid for answers.',
    'overlay_dark': 'Approved ink panel with paper text and paper-filled approved answer badge. Surface opacity uses only approved panel_opacity presets.',
    'overlay_light': 'Approved paper panel, square corners, accent underline. Legacy omitted opacity retains alpha 235; new choices use panel_opacity presets. Actual glyph contrast must pass after compositing.',
    'side_rule': 'Square paper panel with full-height 12px left accent bar; approved answer badge.',
    'bottom_sheet': 'Wide paper sheet with 54px rounded top corners and square bottom; centered accent handle. Must start at y700 or lower and be at least 660px wide.',
    'split_panel': 'Square paper panel with a full-height 82px accent rail; answer label in rail, body text in its own column.',
    'minimal_rule': 'Square paper panel with just a 5px bottom accent rule; approved answer badge.',
    'double_frame': 'Paper panel with an accent outer frame and a fine inset ink frame, inspired by the former framed treatment; independent approved answer badge.',
    'notebook_margin': 'Paper panel with a thin accent margin and small ruled edge ticks, inspired by the former notebook treatment; decoration stays outside the glyphs and answer badge.',
    'top_ribbon': 'Paper panel with a full-width accent top ribbon and a fine ink bottom rule, inspired by the former ribbon treatment; independent approved answer badge.',
    'corner_brackets': 'Paper panel with four inset accent corner brackets instead of a continuous outline; independent approved answer badge.',
    'soft_corner': 'Asymmetric card: rounded top-left, top-right and bottom-right, square bottom-left, thin inset accent rule; independent approved answer badge.',
    'folded_corner': 'Answer-only slip with a clipped/folded top-right corner and fine accent fold; any independently chosen approved badge.',
    'pill': 'Answer-only paper capsule with fully rounded ends, any independent approved badge, and at most two measured text lines. Not valid for body or examples.',
    'italic_photo': 'Unboxed approved Lora Italic example and PRIMJER label directly on photograph. No fade: reject if actual glyph contrast fails.',
    'italic_photo_fade': 'Unboxed approved Lora Italic example and label over photograph, using only renderer-owned approved neutral/palette feathered contrast presets when needed.',
    'italic_footer': 'Unboxed approved Lora Italic example on editorial paper footer below photo, small PRIMJER label and thin separator. No example box.',
}
CATEGORY_CATALOGUE = {
    'rounded': 'Accent chip with moderately rounded corners and ink text.',
    'pill': 'Accent capsule with fully rounded ends and ink text.',
    'ribbon': 'Accent ribbon with a pointed right end and ink text.',
    'underlined': 'Unboxed category text with a thin accent underline; measured photographic contrast or paper ink.',
    'outlined': 'Paper chip with square corners and an accent outline, ink text.',
    'tab': 'Square accent tab with a short ink underline, ink text.',
}
PHOTO_TONE_CATALOGUE = {
    'auto': 'Pillow chooses approved paper or ink glyphs and a neutral black/white fade only if required.',
    'paper_dark': 'Palette paper glyphs; neutral black fade when required.',
    'ink_light': 'Palette ink glyphs; neutral white fade when required.',
    'paper_ink': 'Palette paper glyphs; palette ink fade when required.',
    'ink_paper': 'Palette ink glyphs; palette paper fade when required.',
    'accent_ink': 'Palette accent glyphs; palette ink fade when required.',
    'ink_accent': 'Palette ink glyphs; palette accent fade when required.',
    'accent_dark': 'Palette accent glyphs; neutral dark fade when required.',
    'accent_light': 'Palette accent glyphs; neutral light fade when required; actual contrast must pass.',
    'paper_accent': 'Palette paper glyphs; palette accent fade when required; actual contrast must pass.',
}


def panel_colours(palette, tone='auto', *, dark=False):
    """Approved text/surface pairs, never arbitrary colours or model primitives."""
    if tone not in PANEL_TONES:raise ValueError('Unsupported panel colour treatment')
    ink,paper,accent=palette['ink'],palette['panel'],palette['accent']
    return {'auto':(paper,ink) if dark else (ink,paper), 'ink_paper':(ink,paper),
            'paper_ink':(paper,ink), 'ink_accent':(ink,accent), 'accent_ink':(accent,ink)}[tone]


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
