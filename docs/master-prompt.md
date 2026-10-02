# EasyBosnian project prompt

Build and deploy a fully automated daily content pipeline for my Bosnian-language learning brand, **EasyBosnian**. My Instagram is **@easy_bosnian**, and I have an **EasyBosnian Facebook Page** managed through my personal Facebook account. I am attaching the transparent logo; use **this attached transparent version** as a small corner watermark.

## What it should create

Each day, choose one new beginner-friendly theme and three different Bosnian words, then create a coordinated three-image carousel:

1. **Pitanje dana:** a clear vocabulary quiz with three options, A/B/C, and one correct answer. Keep the answer and explanation in the private review file. **Do not reveal the answer on the quiz image or in any public caption, description or hashtag**—including its letter, correct word, aliases, paraphrased explanation or identifying hints. Invite readers to choose A/B/C without announcing the answer. Check that the other cards do not trivially give it away either.
2. **Znaš li?:** a useful, context-based mini-lesson—a connection, comparison, language pattern or interesting verified fact beyond a simple definition.
3. **Riječ dana:** a short definition written naturally for that theme, followed by a natural example sentence.

Write accurate standard Bosnian with correct grammar and diacritics. Verify meanings and factual claims using reliable sources, but write learner-friendly explanations rather than copying dictionary entries. Generate captions and 3–5 hashtags too.

## Architecture

- A **tool-enabled ChatGPT scheduled task** selects the words and theme, researches and writes all text/captions, checks history, and saves a reviewed JSON package to a private GitHub repository.
- **Cloudflare Workers AI / FLUX** generates three distinct coordinated backgrounds, without text or logos.
- **Python/Pillow** adds the exact Bosnian text, attractive text panels and my transparent corner logo, following the detailed design specification below. Do not ask FLUX to generate lettering.
- Create approved colour palettes and layout templates. ChatGPT selects one shared palette per carousel, but may select a different approved layout for each card to suit its content. Pillow follows those choices while preserving consistent typography, branding and colour treatment.
- **ChatGPT writes each FLUX background prompt after selecting both the card's layout and the carousel's shared colour palette. Describe the composition needed to accommodate the layout: where to leave uncluttered space for headings, text panels and quiz options, and where to position the main subjects so Pillow's overlays do not hide them. Translate the chosen palette into explicit background colour, accent and lighting directions that complement Pillow's text/panel colours; plan contrast in the areas where lettering will appear. Keep all three backgrounds coordinated with that shared palette while making their scenes distinct. Explicitly request no text, lettering or logos. FLUX generates the background only; Pillow draws the text, panels and logo.**
- **GitHub Actions** consumes the package, validates it, generates backgrounds, renders images and publishes to Instagram.
- Use **Cloudflare** for persistent history and image storage because it is a good free option. Choose an appropriate implementation within the free plan. Final JPEGs must be accessible for Instagram to fetch; history and credentials must stay private.

Export Instagram/Facebook cards at 1080×1350; optionally export TikTok versions at 1080×1920.

**Themes and words must never repeat**, including aliases, close variants and renamed versions of the same theme. Check both history and queued content before choosing. Keep this history in Cloudflare. Palettes/layouts may repeat.

## Pillow design specification

Create stylish, coordinated educational cards that show plenty of the background artwork. Avoid generic oversized white rectangles, excessive empty gaps and text that overwhelms the image. Use the exact reviewed text; never silently truncate, alter spelling or lose Bosnian diacritics.

### Typography and positioning

- Bundle **Inter**, with regular, semibold and bold weights and its license. Use bold/semibold for titles and readable regular text inside panels. Verify all Bosnian glyphs: č, ć, š, ž and đ.
- Make the category labels **PITANJE DANA**, **ZNAŠ LI?** and **RIJEČ DANA** compact and consistent. Center their lettering vertically and horizontally using actual glyph bounds; it must not sit too high in the box.
- Quiz question text should appear below its category label, followed by three neatly stacked answer boxes. Position those boxes relative to the question's measured wrapped height, with a compact gap rather than a large fixed empty space.
- Add A/B/C markers exactly once. Align marker and option text vertically within each answer box. Keep widths and spacing consistent.
- For the word/lesson cards, distinguish the category label, featured-word heading and explanatory copy clearly. Separate a lesson and its useful example when that improves readability; do not repeat the same point just to fill a second box.
- Use safe margins, accurate wrapping, measured line spacing and panels sized to their real contents. Check every approved layout with short and long text, including a two-line quiz question.

### Dynamic text density

At the 1080-pixel export size, start with these established body-text settings. Measure the combined instructional body text, excluding category labels/headings:

| Body-text length | Font size | Vertical panel padding |
|---|---:|---:|
| Up to 160 characters | 44 px | 38 px |
| 161–240 characters | 38 px | 30 px |
| More than 240 characters | 34 px | 24 px |

Make panel heights follow the actual wrapped text height. Longer copy must reduce both font size and padding so the Znaš li? panels take less space and reveal more artwork. Add a final fit check using real font metrics; length thresholds alone are insufficient. Preserve every word, keep text readable on a phone, and reject/rewrite overlong copy rather than squeezing it indefinitely. Adapt measurements consistently for TikTok exports.

### Logo and background treatment

- Use the attached **transparent original logo**, small and unobtrusive in a corner, normally bottom-right, with safe edge clearance. Verify its alpha transparency.
- No white square behind the logo, no large logo banner and **no blue “EasyBosnian [date]” footer**.
- Backgrounds should remain distinct but coordinated across the carousel. Use a subtle dark scrim/gradient where needed for heading contrast. Keep light text panels and accent details visually tied to the selected palette without hiding most of the artwork.
- Export all three Instagram/Facebook cards at 1080×1350 with consistent dimensions and margins. FLUX supplies artwork only; Pillow draws all instructional lettering and branding.

### Eight approved text-box layouts

Implement these as genuinely distinct designs, using Inter throughout. ChatGPT chooses an approved layout for each card and records its ID; the layouts may differ within a carousel when that suits the content. For example, the quiz may use framed answer boxes while the mini-lesson uses split-cards. Do not force variation for its own sake: layouts may repeat. Keep the shared palette, font family, category-label treatment, margins and logo placement coordinated so the cards still feel like one set. Pillow applies each card's selected layout.

| ID | Visual treatment |
|---|---|
| editorial | Clean headings, light panels and a slim accent line; balanced, photo-led design. |
| framed | Fine double borders, outlined category label and crisp rectangular answer boxes. |
| notebook | Paper-like panels with a ruled margin, a fine accent line and tab labels. |
| ribbon | Folded ribbon category label, wide accent strip and squared answer markers. |
| split-cards | Separate coordinated panels for lesson/example or definition/example. |
| minimal | Underlined category label, flat panels, restrained dividers and breathing room. |
| rounded | Pill-shaped labels/options, softly rounded panels and friendly bold headings. |
| poster | Heavy headings, stronger accent panels, rectangular labels and bold border blocks. |

### Eleven approved colour palettes

Store this catalog in `data/design-palettes.json`. ChatGPT chooses one palette suited to the theme and backgrounds, saves its ID as `package.design_palette`, and uses it for the whole carousel. Define a per-card `design_template` field in the content schema for the chosen layout ID, rather than requiring one layout for the entire carousel. Do not invent new colours or fonts each run.

| Palette ID | Text ink | Accent | Light panel / heading | Dark scrim |
|---|---|---|---|---|
| gold-cream | #061c42 | #ffcf35 | #fff9e9 | #031428 |
| forest-cream | #14382b | #c5df91 | #f7f8ed | #071b14 |
| terracotta-sand | #44271e | #f0b18f | #fff3e4 | #24120d |
| blue-ice | #10324b | #a8dcf2 | #f0f8fc | #041625 |
| rose-ivory | #402036 | #f3bfd3 | #fff5f7 | #200b19 |
| lavender-pearl | #2d2446 | #d9c8f1 | #faf5ff | #150d25 |
| mint-linen | #123a35 | #bce8d5 | #f2fff8 | #041e18 |
| coral-cream | #4a241e | #ffc5ab | #fff6ec | #260e09 |
| slate-silver | #263244 | #c9d6e7 | #f7f9fc | #0b1420 |
| plum-blush | #372137 | #e7c4df | #fff5fc | #1b091b |
| charcoal-lemon | #28261b | #f5e693 | #fffced | #141308 |

Warm baking/crafts may suit gold-cream; nature forest-cream; earthy subjects terracotta-sand; water/travel blue-ice. Choose other palettes to suit their scenes. Check actual final-image contrast and readability, not just hex values. Show me unpublished examples of the renderer before enabling live posting.

## Authorization: Instagram and Facebook separately

**Do not require linking my Instagram account to my Facebook Page.**

For Instagram, use **Instagram API with Instagram Login** for my professional account. Guide me through the Meta developer app setup, required account roles, Instagram basic/content-publishing permissions, and authorization/token generation. Verify the authorized username is @easy_bosnian, store credentials in GitHub Actions secrets, and implement supported token refresh. Verify current permission names and token requirements.

For Facebook, use an **independent Facebook Pages API authorization** through the personal account that manages my Page. Obtain the required Page permissions, select the exact EasyBosnian Page, and store its Page access token and Page ID separately. Use the same Meta app if supported, or a separate app if necessary. Do not mix Facebook and Instagram tokens or make Page linking a prerequisite.

Guide me step by step through actions only I can complete. Never request passwords or token values in chat. Valid authorization should allow routine posts without asking me each day, while handling expiration/revocation honestly.

## Scheduling, costs and testing

Use **Europe/Sarajevo**: ChatGPT preparation at **16:00 daily** and the pipeline at **16:10 daily**. **Do not create a separate scheduled retry.** Verify scheduled tasks can actually save to GitHub in this environment, and handle delayed/incomplete text preparation clearly. Do not assume ten minutes always suffices or guarantee exact cron execution.

Any deliberate rerun must reuse completed work and avoid duplicate posts. Stop and reconcile uncertain publishing responses rather than blindly reposting.

**Failure reporting:** Configure an available free notification mechanism and document where I will receive failures. Identify the exact failed stage—ChatGPT preparation/queue save, validation, FLUX generation, Pillow rendering, storage, authorization, publishing or publication verification. Include the date/batch, a clear error message, the relevant GitHub run/log link when one exists, and an actionable next step. If the ChatGPT task fails before a GitHub run exists, report that explicitly and link its result if available. State whether anything was published, nothing was published, or publication is uncertain. Preserve diagnostic logs/artifacts without credentials. A missing scheduled run must also be visible: document how it is detected and reported, since a workflow that never starts cannot report its own failure. Never treat a green CI check as confirmed publication or silently swallow failures.

Use free services only: no paid OpenAI APIs, paid posting services, R2 checkout or automatic paid fallback. Verify current Cloudflare/GitHub free quotas. Keep the image provider modular for a later paid OpenAI upgrade.

Start with Instagram only. Show me an unpublished preview, then run one authorized live test and verify its actual publication link. Enable daily posting after I accept the result. Set up Facebook afterward. Investigate TikTok last; do not promise unattended public posting unless its official approval requirements can genuinely be met. Music is optional.

Implement the project in a **new private GitHub repository named `easybosnian-daily-uploads`** under **TifahEfendijaM**. The intended repository is **`TifahEfendijaM/easybosnian-daily-uploads`**. Ignore all other existing repositories, including similarly named EasyBosnian repositories: do not read, modify, delete, trigger workflows in, or use them as this project's source. Verify the exact owner/repository before every repository operation. If the new name is already taken or access is unavailable, explain the issue rather than silently switching to another repository. Use separate deployment/state identifiers so this new project does not accidentally share or overwrite another project's history or publishing state. Keep instructions clear and concise. Report real run status and errors; distinguish saved text, successful tests and confirmed publication. Begin the work and guide me through the necessary setup steps.
