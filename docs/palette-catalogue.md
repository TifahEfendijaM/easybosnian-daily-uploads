# Approved palette catalogue

`data/design-palettes.json` is the authoritative registry of 36 palettes. The original eleven remain unchanged. These eleven additions broaden the catalogue with more tinted surfaces, earthy neutrals and contrasting colour families:

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

The preparation schema and visual-review enum must contain exactly the registry's palette IDs. Do not add arbitrary model-generated colour values or remove archived IDs. The title offers smooth standard or more defined linear edges with equal consideration for both neutral black and white backings. PRIMJER separately offers fully smooth standard or the sharp preset with a smoothly blended upper edge and crisp lower edge. Expanding colours does not alter those edge choices or title shade strengths. PRIMJER strengths now separately expose approved soft/medium/strong IDs without changing its edge geometry.

## Saturated additions

The existing 22 palettes remain unchanged. Fourteen additional families add richer saturated inks and vivid accents, alongside coordinated light surfaces:

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

Every palette already supports a dark surface: choose panel_tone=paper_ink (bright paper text on the dark ink surface) or accent_ink (vivid accent text on dark ink). This is independent of shape, not restricted to overlay_dark. Compare dark and light pairings equally. Keep neutral/light surfaces as available combinations rather than adding palettes that invert the trusted ink/paper roles; this preserves Story/category/contrast compatibility. No new palette is preferred over the original options, and saturated does not mean using every vivid colour at once.
