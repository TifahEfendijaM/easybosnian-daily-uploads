# Trusted visual rendering contract

ChatGPT selects approved declarative data AFTER inspecting actual generated photos. Pillow validates and renders exact reviewed text. `designs.py`, `data/design-palettes.json` and the strict schema in `visual_placement.py` define live enums; `hybrid.py` owns drawing/measurement. Recovery and exact-card retention follow `element-design-recovery.md`. Preparation/FLUX scene rules belong to `preparation-task.md`, not visual review.

## 1. Inputs and composition decisions

The reviewer sees ONLY complete actual photographs and exact feed crops, exact public copy, compact measured fit profiles and whitelisted recent accepted-choice metadata (up to five completed daily runs, including reruns). No rendered/styled references or private answer keys. `default_plan` is solely an uncertainty fallback, never a design recommendation. Missing recent context is explicitly incomplete, not invented, and does not block fresh review.

Review ALL compatible catalogue options before choosing; catalogue order/familiarity is not a ranking. Compare several materially different treatments and plausible upper/middle/lower, left/right or split placements against each photo's negative space, exact text length, hierarchy, subject visibility and overall balance. A top placement is valid when best; it has no automatic preference. Neither rare styles nor variety itself are goals. If recent accepted treatments/visually similar families have dominated, prefer a different suitable, appealing, readable, harmonious alternative, even if slightly less optimal alone; never an unsuitable choice. This design-history preference does not override compatibility, safety or full-photo rules.

For ordinary lesson/word posts full-background hybrid is the STRONG DEFAULT, with no priority among its approved body treatments. First try several independent full-photo placements. Separate middle photo windows remain available as an exceptional last resort when long exact copy cannot fit elegantly or readable overlays would hide identifying subjects/actions/faces. Do not select them merely for tidiness, novelty or ease. Editorial supports lesson/word only: plain body ABOVE a wide cover-fit photo, italic_footer BELOW, with 24px gaps. Preserve required subjects through the centered cover crop; otherwise use full-background hybrid or a complete contained photo. Never default to a tiny square photo.

Choose per-card palettes independently against natural materials, light, dominant colours and readable panel/text contrast. No shared-batch/quiz-matching or blue/yellow brand-palette preference; never recolour photos. The preparation palette is fallback only. Compare EVERY approved palette, without first/last/familiar shortcuts, then apply the following existing repetition exception:

- For EVERY palette, normally at most TWO uses in any consecutive NINE image cards including the candidate. Count the preceding eight known applied palettes and earlier choices in this batch in quiz→lesson→word order.
- Also avoid a SECOND use in the SAME BATCH. At either threshold compare all other approved palettes and select a suitable alternative even if the repeated one is slightly preferable. Only when absolutely no other palette suits the photo may `palette_exception=no_other_suitable_palette` permit reuse; otherwise `none`.
- Never choose clashing colours or use random rotation. This alternatives-first rule takes precedence over a repeated single best match, not over suitability. Observed fallback palettes count for later choices but are not forcibly recoloured. Non-palette recent-choice context excludes fallback decisions and earlier fixed/random example presets; palette provenance remains independent.

## 2. Declarative fields and typography

Cards expose `confidence` (high/uncertain), `design` (hybrid/editorial), approved `palette`, `palette_exception`, `category_style`, `category_tone`, `heading_tone`, `heading_fade`, `photo_window`, and ordered `blocks`. Blocks expose role/style, x/y/width, font_size, line_spacing, optional max_lines (null or 1–12) and wrapping (balanced/natural). Body/answers also expose panel_tone and panel_opacity=100; answers alone expose marker_style, examples alone photo_tone/fade_style. Preserve every exact source role in array order; array order need not impose vertical order except ordered quiz choices.

No proposal text/manual line breaks, drawing code/primitives, CSS, font filenames, custom colours/hex, arbitrary opacity, border/radius/shadow/filter definitions or custom rendering instructions. Category/title anchors and fonts/sizes remain renderer-controlled. `design_template` is legacy-readable, ignored by rendering and omitted from fresh content.

| Role | Target size | Loaded face | Leading multiplier |
|---|---|---|---|
| body | 32–48px | Inter Regular | 1.20–1.55 |
| answers | 32–46px | Inter Regular | 1.20–1.55 |
| example | 28–40px | Lora Italic | 1.20–1.55 |

Pillow computes final height from exact glyphs and actual baselines, with at least 4px between adjacent accented rows; a single line has no inter-line collision. Balanced wrapping distributes the minimum lines without tiny orphans; natural wrapping is greedy. Unicode spaces reconstruct exact source; NBSP/narrow NBSP/word joiners remain unbreakable. Never strip/normalize diacritics or combining characters for drawing. max_lines is a rejection constraint, never truncation permission. Category letters use actual glyph bounds and a shared capital baseline so Š/Č accents do not shift the lettering downward.

Use the original transparent logo small and unobtrusive, normally bottom-right with safe clearance and its alpha preserved. No white square, large logo banner or blue “EasyBosnian [date]” footer. Keep 1080×1350 feed and 1080×1920 Story exports with consistent safe margins.

Fit profiles include exact text/width/font/leading, complete height, line count, padding, label and separator. Measurement-family deduplication never merges style renderers. Profiles are data, not a restricted creative menu: all approved intermediate widths/fonts/leading/natural wrapping remain available. Do not scale heights linearly across widths/fonts or estimate an example from a body profile with different wrapping. A leading-only change adjusts height by (line_count−1) × change in rounded font_size*line_spacing, subject to glyph clearance.

## 3. Real body and answer treatments

| ID | Material treatment | Validity |
|---|---|---|
| rounded | paper panel, moderate round corners, inset accent rule | hybrid body/answer |
| outlined | square paper, accent outline/inset rule | hybrid body/answer |
| plain | unboxed paper copy, no panel/rule | editorial body only |
| overlay_dark | ink panel, paper text | hybrid body/answer |
| overlay_light | square paper, accent underline | hybrid body/answer |
| side_rule | square paper, full-height left accent bar | hybrid body/answer |
| bottom_sheet | wide sheet, rounded top/square bottom, accent handle | hybrid body/answer; y≥700, width≥660 |
| split_panel | square paper, wide accent rail/separate text column | hybrid body/answer |
| minimal_rule | square paper, bottom accent rule | hybrid body/answer |
| double_frame | accent outer frame, fine inset ink frame | hybrid body/answer |
| notebook_margin | accent margin, ruled edge ticks outside glyphs/badge | hybrid body/answer |
| top_ribbon | accent top ribbon, fine inset bottom rule | hybrid body/answer |
| corner_brackets | four inset accent brackets, no continuous frame | hybrid body/answer |
| soft_corner | round top-left/top-right/bottom-right, square lower-left | hybrid body/answer |
| pill | capsule with fully rounded ends | answers only, at most two measured lines |
| folded_corner | clipped/folded top-right slip | answers only |

Every ID has materially distinct Pillow drawing behavior. Hybrid body/answers MUST be bounded panels, never unboxed text over photos/fades. Former caption is invalid. PRIMJER never uses this catalogue. Answer panel style and badge shape are independent; any answer treatment may combine with circle/rounded_square/square/triangle. Coordinated choices are often appealing; coherent mixtures remain allowed. Never signal the correct answer through design.

Answers have independent x/y/width and typography, ordered A→D by y then x. Staggered regions/left-right arrangements remain valid; do not mechanically stack or snap to grids. Intentional shared rows use exactly equal y and coordinated font/leading. Pillow uses a shared measured font cell to align equal-font/equal-line-count panels/baselines despite accents/descenders; unequal line counts can need unequal heights. A 2×2 grid requires four existing choices; three need an intentional three-card arrangement, not an accidentally missing fourth. The visual reviewer cannot invent/remove/rewrite choices.

## 4. Categories, panel colours and opacity

Categories: rounded (moderate corners), pill (capsule), ribbon (pointed right end), underlined (bare text/rule), outlined (paper chip/accent outline), tab (square accent tab/inset rule). All keep fixed Inter typography/anchors and correctly aligned Bosnian capital accents. NEVER put a fade/scrim/glow/shadow behind a category, including underlined. Bare labels must pass glyph contrast without shading; choose a bounded chip otherwise. Pillow rejects unreadable bare labels rather than adding shade or silently changing their design. Title shading is clipped below the protected category strip.

Panel/category tones use approved palette roles, named text_then_surface: auto (style default), ink_paper, paper_ink, ink_accent, accent_ink. Compare harmonious readable pairings rather than assuming only white/black text. Plain editorial body requires auto/100. Every fresh bounded body/answer panel is fully opaque at 100%, including repairs/fallback/reuse: no random draw or model-selected transparency. Glyphs, badges/rules remain opaque. Category chips, unboxed copy and preset fades are separate controls.

## 5. Title and separate PRIMJER treatments

Title heading_tone allows auto, paper_dark, ink_light, paper_ink, ink_paper, accent_dark, accent_light. Title text may use neutral white/black or palette paper/ink/accent; its backing is ONLY neutral BLACK or WHITE. PRIMJER photo_tone independently keeps ALL neutral and palette-coloured pairings in PHOTO_TONE_CATALOGUE. Give neutral black/white and EVERY approved palette-coloured PRIMJER shade backing equal consideration: do not automatically favour neutral backings or treat palette-coloured backings as secondary exceptions. Compare every compatible pairing and choose the approved text/backing combination best suited to the actual photograph, palette harmony and readability. Light text on dark remains the usual direction; choose dark text/light backing when the photograph suits it better, not solely for variety. This brightness/contrast preference does not favour black over approved dark palette colours or white over approved light palette colours. Equal consideration does not mean random selection, equal usage frequency or forced variety.

Title heading_fade: standard (smooth eased edges) or defined (more defined full-width linear edges). Give BOTH equal consideration for BOTH backing colours and let ChatGPT choose the better fit; no preferred preset, rotation or random draw. Automatic selection of a white backing preserves the chosen preset. Favour gentle title shading when needed, not a pronounced precautionary band; weak/no shade remains valid on readable photos. Do not choose a worse-fitting colour pair merely to avoid shading.

PRIMJER has ONLY italic_photo (unshaded photo, must pass as-is), italic_photo_fade (photo with trusted contrast backing), italic_footer (unboxed editorial paper footer/separator). All use Lora Italic and renderer-owned PRIMJER label, never a box. For italic_photo_fade choose standard (smooth compact taper) or sharp (crisp straight translucent strip, no feather/rounding/border), equally considered with neither preferred; compare the actual photo rather than alternate/randomize. Both extend 18px BELOW the final row; standard has a 48px taper, sharp 12px padding above the label. Use inactive standard for unshaded/photo-footer and paper headings; paper heading/footer tones use auto. No fade is added to italic_photo.

Pillow alone owns fade geometry and contrast-driven strength, never model dimensions/opacity/softness. Titles retain 100px extent; standard uses power 2.5, defined retains distinct linear edges. Title alpha candidates are 12,24,36,48,54,66,78,90,102,114,126,130,144,170,210,240, with fine 2-alpha steps for white where available. Use the first passing 3:1 glyph contrast. Necessary core shading spans measured letters+20px, easing over 180px horizontally to 35% elsewhere for black, 10% for white. PRIMJER retains its original contrast-driven alpha sequence. Text remains above the logo strip; its shade may extend into the footer before the unchanged original logo is composited on top.

Judge the combined weight of title AND example shades across the WHOLE photo, even far apart. If heavy/striped/crowded, strongly prefer shading only ONE. When the title is readable without shading, prioritise the PRIMJER backing rather than the title backing. If both need shading, favour a readable composition with lighter title shading and stronger support for PRIMJER, rather than the reverse, whenever readability allows. The larger title can usually stand on its own; the smaller italic example benefits more from a backing. Achieve this hierarchy through approved text colours and independent example placement; Pillow alone controls actual strength, with no custom strength/opacity field. Unshaded italic_photo and both shades remain available when appropriate. Do not add unnecessary shade merely to enforce the preference, sacrifice contrast/harmony or suppress required title protection. Readability takes priority; this is not a global change to either shade preset.

## 6. Independent placement and geometry

Body and photographic PRIMJER are independent, not an attached pair. The example may be far BELOW an upper body near the logo-safe boundary, far ABOVE a lower body or elsewhere when best. There is no maximum gap, required adjacency or imposed vertical order; hundreds of pixels can be intentional. Close grouping is equally valid when best. Maintain 32px minimum example clearance for EVERY shade/design, not a target distance. Editorial/footer and Story order stays fixed.

Prefer one exact-copy example line whenever it fits safely at the chosen font: do not create artificial wrapping with a narrow column. Pillow may widen ONLY the example and shift it horizontally to the nearest tested safe slot, preserving y/font/leading/text/style/colours/other blocks, then recheck everything. If unsafe/unreadable retain original wrapping; no truncation/font shrinking/other-block movement or extra model call for this adjustment. Report applied x/width changes. Long examples wrap normally.

Blocks stay within x64..1016, below header_end+24 (fixed feed heading starts y174), ending by y1170 above the logo. Editorial italic_footer alone may end by y1286 with right edge≤x880. Body/answers need ≥8px measured separation (14–24px breathing room preferred); editorial body/photo/footer need 24px. Panels occupy their FULL rectangles; unboxed collision bounds use visible glyph/label/rule width, not unused wrapping space. Declared geometry still stays safe.

Photo windows fix x64/width952, y250..770, height400..800 (240..800 for visual identification). hybrid uses contain; editorial cover. A contained photo is complete, with photographic examples at least 20px inside its actual bounds. Body/answers stay outside separate windows; visual-naming quizzes require question → complete contained photo → all choices. Panel coverage cannot exceed 49% of the card. Semantic face/object/action preservation remains the visual model's judgment; geometry cannot guarantee arbitrary subject detection.

## 7. Validation, recovery, provenance and compatibility

Pillow loads bundled licensed Inter body/categories, Lora SemiBold titles and Lora Italic examples, measures wrapping/final heights and rejects unsupported fields/combinations, reordered/lost roles, invalid sizes/leading, clipping/truncation, header/logo/window collisions, overlap, excessive coverage and unreadable pixels. Body/example glyph contrast is ≥4.5:1, titles ≥3:1, sampled at actual glyph masks against final composited surfaces, including neighbouring fades. Valid proposals are never moved for aesthetics.

Layout and palette acceptance are independent. Missing/unapproved/low-contrast palette may be replaced with the preparation palette while preserving a valid model layout; a valid model palette may survive failed elements/layout. For photo contrast failure try the unchanged layout with the preparation palette before discarding safe layout choices. Uncertain confidence replaces layout but can keep a valid palette; unavailable/malformed outer review uses full fallback. Isolatable per-card/element failures do not discard valid siblings. Apply the bounded position repair, up-to-three proposals and smallest-element recovery in element-design-recovery.md, preserving accepted fields and rechecking collisions/pixels. Integrity failures remain fatal. Full fallback's PRIMJER targets the lower safe edge (bottom y1150), moving upward only as measured height requires; an unreadable/unrenderable final fallback stops publication.

Initial visual review deadline is 600 seconds, defect-feedback proposals 180; service failures receive no retry. Store fixed safe rejection reasons and only schema-approved rejected parameters BEFORE fallback, even if fallback fails; unknown prose becomes unclassified. Reports separately show layout (chatgpt/mixed/reused/fallback), palette source/reason, preserved/replaced elements, requested/applied position/width adjustments, design attempts and photo inspection/selected attempt. Historical missing provenance stays unknown, never inferred from matching IDs; compatibility outcome is layout-only. Do not report successful repair as full fallback or expose arbitrary model prose, private notes, answers or credentials.

Stories retain trusted treatment B, exact source photo/copy and final per-card palette/category choice, with Inter body and unboxed Lora Italic footer plus accent separator; no independent design call. Prepared JPEGs are versioned and reused unchanged after credential persistence. Legacy design_template, soft/defined example fades, soft title fades and earlier opacity strings/numeric values/omitted defaults remain readable, never fresh choices. Earlier fixed/random/opacity report provenance stays historically accurate, not rewritten or treated as current model choices. Keep current manifest/version handling; no Worker/database/scheduler change is implied by this contract.
