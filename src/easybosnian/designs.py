"""Reviewed Pillow styles: data choices, never model-generated drawing code."""
DESIGNS = ('hybrid', 'editorial')
BODY_STYLES = ('rounded', 'outlined', 'plain')
EXAMPLE_STYLES = ('italic_photo', 'italic_footer', 'boxed')
STYLE_CATALOGUE = {
    'hybrid': 'Full photographic background (or contained photo window), rounded accent category badge, Lora title; rounded or outlined Inter explanation/answer panels. Examples: unboxed Lora italic over a calm photo area, or a rounded example panel.',
    'editorial': 'Lesson/word only: paper page, tracked plain category with a thin underline, Lora title, plain Inter explanation, large wide photograph, thin separator then unboxed italic example on paper below the photograph. All positions chosen after inspecting the image; no forced colour atmosphere.',
    'rounded': 'Paper panel with rounded corners and an inset accent rule for explanations; circular answer label for quiz choices.',
    'outlined': 'Paper panel with square corners and a thin accent outline; same measured padding and readable text/answer marker.',
    'plain': 'Unboxed Inter explanation on the editorial paper page, outside the photograph.',
    'italic_photo': 'Small PRIMJER label and pure Lora Italic text directly over the photo. Neutral local shading only when contrast requires it; avoid faces and important objects.',
    'italic_footer': 'Thin separator, small PRIMJER label and pure Lora Italic text on the editorial paper footer below the photo. Reserve the fixed logo corner.',
    'boxed': 'Rounded paper PRIMJER panel with Inter example copy and an inset accent rule.',
}
