"""Trusted declarative catalogue. Every treatment has a real Pillow renderer."""
import math
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
# Fresh reviews choose approved colours and one of two fixed fade presets.
REVIEW_PHOTO_TONES = PHOTO_TONES
# Titles retain approved text colours, with neutral backing colours only.
REVIEW_TITLE_TONES = ('auto','paper_dark','ink_light','paper_ink','ink_paper','accent_dark','accent_light')
TITLE_TONE_CATALOGUE = {
    'auto':'White or black title text; matching neutral black or white fade only when required.',
    'paper_dark':'White title text; neutral black fade when required.',
    'ink_light':'Black title text; neutral white fade when required.',
    'paper_ink':'Palette paper-coloured title text; neutral black fade when required.',
    'ink_paper':'Palette ink-coloured title text; neutral white fade when required.',
    'accent_dark':'Palette accent-coloured title text; neutral black fade when required.',
    'accent_light':'Palette accent-coloured title text; neutral white fade when required.',
    'accent_ink':'Legacy palette accent-coloured title text; neutral black fade when required.',
    'ink_accent':'Legacy palette ink-coloured title text; neutral white fade when required.',
    'paper_accent':'Legacy palette paper-coloured title text; neutral black fade when required.',
}
PANEL_TONES = ('auto', 'ink_paper', 'paper_ink', 'ink_accent', 'accent_ink')
REVIEW_FADE_STYLES = ('standard', 'defined')  # titles
REVIEW_EXAMPLE_FADE_STYLES = ('standard', 'sharp')
TITLE_FADE_STYLES = (*REVIEW_FADE_STYLES, 'soft')  # soft is archive-only
FADE_STYLES = (*TITLE_FADE_STYLES, 'sharp')  # sharp is an approved example-only preset
FADE_CATALOGUE = {
    'standard': 'Smoothly eased edges within protected bounds; gentler outer title fade.',
    'defined': 'Earlier full-width linear shade with more defined edges, not the smooth preset. PRIMJER backing extends 18px below the last row before its 48px taper.',
    'sharp': 'PRIMJER-only full-width translucent band with crisp straight top/bottom boundaries, 12px above the label and 18px below the final row; no feather, rounded box or border.',
}
PANEL_OPACITIES = {'solid': 255, 'soft': 230, 'translucent': 191}
PANEL_OPACITY_RANGE = (85, 100)
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
    'overlay_dark': 'Approved ink panel with paper text and paper-filled approved answer badge. Explanation surface opacity is assigned 85–100 percent; answers are fully opaque.',
    'overlay_light': 'Approved paper panel, square corners, accent underline. Legacy omitted opacity retains alpha 235; new explanations use 85–100 percent and answers use 100 percent. Actual glyph contrast must pass after compositing.',
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
    'italic_photo_fade': 'Unboxed Lora Italic example and label over either standard (smoothly fading edges) or sharp (crisp straight-edged translucent strip), chosen for the actual photograph without a preferred preset. Both extend below the text. Approved colours remain selectable; geometry/strength are renderer-owned. Earlier defined treatments remain readable in saved plans.',
    'italic_footer': 'Unboxed approved Lora Italic example on editorial paper footer below photo, small PRIMJER label and thin separator. No example box.',
}
CATEGORY_CATALOGUE = {
    'rounded': 'Accent chip with moderately rounded corners and ink text.',
    'pill': 'Accent capsule with fully rounded ends and ink text.',
    'ribbon': 'Accent ribbon with a pointed right end and ink text.',
    'underlined': 'Unboxed category text with a thin accent underline; actual photographic contrast must pass without a fade, or use paper ink on a paper layout. Choose a bounded category chip when unshaded text would be unreadable.',
    'outlined': 'Paper chip with square corners and an accent outline, ink text.',
    'tab': 'Square accent tab with a short ink underline, ink text.',
}
PHOTO_TONE_CATALOGUE = {
    'auto': 'On photographs Pillow chooses white/black glyphs with the matching black/white fade only if required; paper layouts retain palette ink.',
    'paper_dark': 'White glyphs; fixed neutral black fade when required.',
    'ink_light': 'Black glyphs; fixed neutral white fade when required.',
    'paper_ink': 'Palette paper glyphs; palette ink fade when required.',
    'ink_paper': 'Palette ink glyphs; palette paper fade when required.',
    'accent_ink': 'Palette accent glyphs; palette ink fade when required.',
    'ink_accent': 'Palette ink glyphs; palette accent fade when required.',
    'accent_dark': 'Palette accent glyphs; neutral dark fade when required.',
    'accent_light': 'Palette accent glyphs; neutral light fade when required; actual contrast must pass.',
    'paper_accent': 'Palette paper glyphs; palette accent fade when required; actual contrast must pass.',
}


def valid_panel_opacity(value, *, legacy=True):
    """A bounded percentage, or an old preset retained for saved plans/reports."""
    minimum=50 if legacy else PANEL_OPACITY_RANGE[0]
    return ((legacy and isinstance(value, str) and value in PANEL_OPACITIES) or
            (type(value) in (int, float) and minimum <= value <= PANEL_OPACITY_RANGE[1]
             and math.isfinite(value)))


def panel_alpha(value):
    """Convert the declared surface percentage to Pillow's 8-bit alpha only."""
    if not valid_panel_opacity(value):raise ValueError('Panel opacity outside the approved range')
    return PANEL_OPACITIES[value] if isinstance(value, str) else round(value * 255 / 100)


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
