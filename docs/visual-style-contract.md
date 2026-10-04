# Trusted visual rendering contract

ChatGPT selects approved data after inspecting the generated photographs. Pillow validates and draws the exact source. No visual child ever writes drawing code or changes copy.

## Allowed data

Each card has `confidence`, `design` (`hybrid` / `editorial`), an approved `palette` ID, `photo_window` and ordered `blocks`. Palette IDs come only from `data/design-palettes.json`. A photo window is null or `{y, height, fit}`: x64/width952 are fixed, y250–770, height400–800 (240–800 for visual-identification quizzes), fit `contain` for hybrid or `cover` for editorial. Full-background hybrid uses the feed crop. A contained photo remains complete; an editorial cover crop requires a visual assessment that required subjects survive.

Each block allows only `role`, `style`, `x`, `y`, `width`, `font_size`, `line_spacing`, optional `max_lines` (null or1–12) and `wrapping` (`balanced` or `natural`). All text comes from the exact reviewed card; there is no text field in the proposal. Blocks preserve source order and every role. Labels/title typography stays renderer-controlled.

| Role | Font targets | Face | Leading |
|---|---|---|---|
| body | 32–48px | bundled Inter Regular (SemiBold for caption) | 1.20–1.55 × font size |
| answers A–D | 32–46px | bundled Inter Regular | 1.20–1.55 × font size |
| PRIMJER/example | 28–40px | bundled Lora Italic | 1.20–1.55 × font size |

Leading must additionally leave at least4px between measured full accented glyph bounds. Pillow computes height; the model cannot specify height or replace text with manually line-broken copy. `max_lines` rejects overlong exact text rather than truncating it. Natural wrapping is greedy; balanced wrapping distributes the minimum number of lines without tiny orphan lines. Unicode spaces preserve exact reconstruction; NBSP, narrow NBSP and word joiners remain unbreakable. Diacritics and combining characters are never stripped or normalised for drawing.

## Ten real body treatments

| ID | Trusted renderer | Restriction |
|---|---|---|
| rounded | opaque paper, rounded corners, inset accent rule/circular answer marker | hybrid |
| outlined | square paper, accent outline, square outlined answer marker | hybrid |
| plain | unboxed copy on paper, no panel or rule | editorial body only |
| overlay_dark | opaque ink panel, paper text and rectangular paper marker | hybrid |
| overlay_light | fixed translucent paper preset, accent underline; glyph contrast tested on actual composited photo | hybrid |
| side_rule | square paper with full-height left accent bar, unboxed answer letter | hybrid |
| caption | unboxed SemiBold photo copy with separator and trusted neutral contrast fade | full-background hybrid body only, max3 measured lines |
| bottom_sheet | wide paper sheet, rounded top/square bottom, centered accent handle | hybrid, y>=700, width>=660 |
| split_panel | square paper, wide accent rail, separate text column | hybrid |
| minimal_rule | square paper, bottom accent rule, inline answer label | hybrid |

Every ID reaches distinct Pillow drawing behavior. None is a metadata alias. Editorial supports only plain body and italic_footer example around its separate photograph. Quiz cards remain hybrid with clear panel answers; visual identification requires every answer below the complete photo.

## Separate PRIMJER enum

Only `italic_photo`, `italic_photo_fade`, `italic_footer` are valid. All use Lora Italic and a small renderer-owned PRIMJER label, never a box. `italic_photo` uses the photograph directly and fails if glyph contrast is insufficient. `italic_photo_fade` may apply the fixed neutral feathered contrast presets; the model cannot choose alpha, colour, filter or fade geometry. `italic_footer` uses the editorial paper below the photograph with a thin separator. Stories use an unboxed italic paper footer.

## Independent trusted checks

The JSON schema rejects extra fields, mixed role/style enums, invalid typography and unapproved palette/design/window choices. Pillow reloads actual fonts, wraps exact text, measures glyph extents/final height and rejects clipping, leading collisions, overlap, lost/reordered roles or unsupported design combinations. Blocks stay within x64–1016, below the measured heading+24 and above y1170. Editorial examples alone may end at y1286, with right edge<=880 to protect the logo. Blocks need14px separation; editorial body/photo/footer need24px gaps. Hybrid photo examples must stay20px inside the actual contained photo. Body/answer treatments cannot overlap a separate photo; opaque/semitransparent panel coverage cannot exceed49% of the card. Full-background subject recognition is a visual judgment; geometric protection does not claim to detect arbitrary faces/objects.

Body/example glyph contrast is at least4.5:1; title contrast is at least3:1. Photo-text contrast is sampled at actual glyph-mask locations against the final composited surface, including neighbouring preset fades. Approved palette ink/paper/accent contrast is checked. No proposal may supply drawing primitives, replacement text, code, CSS, font paths, custom hex colours, alpha, borders/radii/shadows or arbitrary filter definitions.

Invalid/unavailable/uncertain visual proposals use the existing measured deterministic hybrid fallback, never a second model or FLUX call. A per-card measured rejection uses the preparation palette and trusted default font sizes/spacing. If the fallback cannot preserve exact text and readability, the run fails before publishing. Integrity failures remain fatal. Stories keep treatment B and select the matching feed card's final approved palette. Final safe data is captured in the private placement result and GitHub report; no raw model prose is logged.

Legacy `design_template` remains readable but ignored, has no effect on bytes, and is absent from newly saved content. Rendering manifest version4 prevents reuse of artwork generated under an older contract. No Worker/database/scheduler deployment is required. Repository merge activates this contract for subsequent runs.
