# Approved palette catalogue

`data/design-palettes.json` is the authoritative registry of 36 palettes. The catalogue began with eleven palettes. These eleven additions broadened it with more tinted surfaces, earthy neutrals and contrasting colour families:

| Palette ID | Colour character |
|---|---|
| burgundy-oat | Burgundy ink, muted rose accent, warm oat paper |
| olive-stone | Olive ink, sage accent, green-grey stone paper |
| indigo-mist | Indigo ink, periwinkle accent, blue mist paper |
| copper-linen | Brown ink, copper accent, natural linen paper |
| teal-seaglass | Deep teal ink, turquoise accent, sea-glass paper |
| aubergine-apricot | Aubergine ink, apricot accent, warm blush paper |
| espresso-almond | Espresso ink, almond accent, warm neutral paper |
| graphite-chalk | Graphite ink, silver-grey accent, neutral chalk paper |
| cobalt-peach | Cobalt ink, peach accent, cool blue-white paper |
| ochre-parchment | Brown-ochre ink, golden accent, yellow parchment paper |
| pine-rose | Pine ink, dusty rose accent, pale sage paper |

All palettes retain the same trusted ink/accent/panel/scrim roles and existing selectable colour pairings. Dark and light card treatments can still use these roles in their supported combinations. Fresh image review compares all old and new palettes against the actual photograph; there is no preference for the additions or for catalogue order. Existing per-image selection, all-palette repetition rules and measured final-pixel contrast checks continue to apply. Photographs are never recoloured to fit a palette.

The preparation schema and visual-review enum must contain exactly the registry's palette IDs. Do not add arbitrary model-generated colour values or remove archived IDs. The current title/PRIMJER edge, strength and placement rules are authoritative in `docs/visual-style-contract.md`; palette refinements do not change those rules.

## Saturated additions

Fourteen additional families expanded the earlier 22 with richer saturated inks and vivid accents, alongside coordinated light surfaces:

| Palette ID | Colour character |
|---|---|
| royal-blue-sun | Royal blue and bright yellow |
| emerald-lime | Emerald and lime |
| ruby-cream | Ruby and vivid pink |
| violet-citrus | Violet and golden citrus |
| ocean-tangerine | Ocean blue and tangerine |
| magenta-porcelain | Magenta and bright pink |
| scarlet-vanilla | Scarlet and golden yellow |
| peacock-coral | Peacock teal and coral |
| sapphire-lime | Sapphire and lime |
| grape-lemon | Deep grape and lemon |
| paprika-aqua | Paprika and aqua |
| ultramarine-orchid | Ultramarine and orchid |
| cherry-lime | Deep cherry and vivid lime |
| petrol-cyan | Deep petrol blue and bright cyan |

Every palette already supports a dark surface: choose panel_tone=paper_ink (bright paper text on the dark ink surface) or accent_ink (vivid accent text on dark ink). This is independent of shape, not restricted to overlay_dark. Apply the current lesson/word and quiz surface-selection rules in `docs/visual-style-contract.md`. Keep neutral/light surfaces as available combinations rather than adding palettes that invert the trusted ink/paper roles; this preserves Story/category/contrast compatibility. No new palette is preferred over the original options, and saturated does not mean using every vivid colour at once.

## Approved dark-colour refinements - 27 October 2026

Four existing ink roles were refined after side-by-side review: Espresso-Almond `#352923` to `#492817`, Plum-Blush `#372137` to `#4b1c49`, Slate-Silver `#263244` to `#173957`, and Olive-Stone `#29321a` to `#2d4218`. Their paper/panel, accent and scrim colours and all palette IDs remain unchanged; the catalogue still contains 36 palettes. These richer dark inks also supply dark lettering wherever the approved pairing uses the ink role. Every ink/paper and ink/accent pair remains subject to measured contrast checks. Palette expansion and colour refinements do not override the current visual-style contract.

## Approved light-surface refinements - 27 October 2026

After reviewing local swatches and saved-photo comparisons, three paper/panel roles were refined: Espresso-Almond `#e7ded2` to `#f1e5d5`, Copper-Linen `#ecdcc6` to `#f4e2c9`, and Olive-Stone `#e4e6cf` to `#edf0d6`. Their current ink, accent and scrim roles remain unchanged. The paper role also supplies light lettering and Story backgrounds in the supported pairings. The catalogue remains at 36 palettes; no expansion or further colour proposals are applied. All existing contrast and per-card design-selection rules continue to apply.
