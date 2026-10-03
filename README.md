# EasyBosnian daily uploads

Private repository **TifahEfendijaM/easybosnian-daily-uploads**. The existing Cloudflare Worker starts one GitHub workflow at **05:00 daily Europe/Sarajevo**. The clock handles daylight saving automatically. GitHub has no schedule trigger, and there is no automatic retry or missing-run monitor.

One job follows a straight path: a GPT agent through the existing ChatGPT subscription researches and reviews content → the wrapper saves today's Cloudflare history row → refreshed cloud credentials are persisted privately → Pillow renders three cards using Free FLUX backgrounds → Instagram, Facebook and Buffer TikTok publish → Instagram and Facebook upload the same cards as image Stories after their respective feed posts succeed. Publication starts immediately after preparation. No awake Mac or paid OpenAI API is needed.

## Three modes

| Mode | Content | Images | Posting |
|---|---|---|---|
| verify (default) | Reads history and verifies connections/workspace only | None | None |
| preview | Reuses today's row, or researches/saves it if absent | Renders private cards | None |
| daily | Always researches and overwrites today's content | Renders replacement cards | All enabled platforms |

The user chose complete same-date overwrite. A daily run after a preview prepares replacement content rather than posting that preview's exact cards. Earlier same-day themes/words are removed from future novelty checks. Other dates' history remains. Previewed content counts toward history until replaced, even if never posted.

**DAILY_POSTING_ENABLED is the live kill switch.** Every live entry point checks it independently of event type. verify and preview do not depend on it. Separate FACEBOOK_POSTING_ENABLED, TIKTOK_POSTING_ENABLED, INSTAGRAM_STORIES_ENABLED and FACEBOOK_STORIES_ENABLED switches control those publishers. Facebook Stories also require Facebook feed publishing to be enabled and confirmed in the current run. PREPARATION_DISPATCH_ENABLED controls only Cloudflare starts.

## History and validation

D1 history is the single source of truth: each new daily row has one date, theme, three words with equivalence keys, and complete reviewed content. Older user-supplied uploads may be metadata-only legacy_word_history rows with estimated historical dates, inferred themes and all supplied lemmas. They still prevent repeats, but contain no invented card text/reviews and cannot be rendered or published. There is no queue directory, content commit/read-back, package hash, reservation ledger or publication state machine. A minimal separate publication_ids table stores only known provider IDs and account/date identity for explicitly requested replacement cleanup. Theme/word comparisons still check aliases and normalized spelling, while GPT performs semantic review and source research. Quiz answer text and letters remain private outside the quiz choices. A visual naming quiz may show the object it asks readers to name; other quiz scenes must be relevant without solving the tested unknown. All learner-visible copy stays in Bosnian, and foreign-word translation questions are rejected. Znaš li? favours practical situations, useful comparisons and interesting researched facts over routine grammar drills. Schema, measured text fit, contrast and diacritics checks reject invalid content without truncation.

Pillow renders exact text and the original transparent watermark onto 1080×1350 cards. Body sizes are 44/38/34 px at 160/240-character boundaries. Licensed Inter, semibold headings, rounded panels, inset accent lines and a PRIMJER label give the definition/example a clearer hierarchy. GPT selects one shared palette and per-card layouts from the approved catalogs. FLUX receives short, explicitly photorealistic photography prompts with real subjects, natural light, realistic textures and plain colour names and at most one broad framing direction; Pillow handles text and branding.

KV images expire after 14 days. Only final card/Story JPEGs receive random public URLs for social platforms to fetch. Shared backgrounds are cached, and a reviewed content replacement invalidates that date's caches. Instagram and Facebook Stories use 1080×1920 (9:16). Riječ dana and Znaš li? use B: a full photo above separate text panels. Pitanje dana uses A (the full feed card over a softly blurred original photo) unless quiz_format is visual_identification; that visual naming quiz uses B in both its Story and regular 1080×1350 slide. Regular word/lesson posts retain their current design. Exact copy, full-photo/card fit, logo, measured sizing and contrast remain; no extra FLUX request is made. Facebook uses separate unpublished photo uploads because Meta forbids reusing previously published feed media IDs, then checks the returned Stories against the Page. No extra FLUX generation or new credentials are needed. Highlights and TikTok Stories require manual action; the documented TikTok/Buffer APIs do not expose a Story publishing option.

## Deliberate operational tradeoffs

Only cron delivery is deduplicated through preparation_dispatches. Publication has no saved intent, reconciliation or already-published gate. A manual daily rerun can create another post, including after an ambiguous response. Returned post IDs and verification results are kept in private run artifacts, not used to suppress later runs. A platform failure does not stop other enabled feed publishers.

Failures that occur during a run write build/failure.txt and open a private GitHub issue with the failed stage and actual publication status. When no run starts, no notification is sent. All Healthchecks/watchdog support is removed.

## Setup and deployment

See [authorization](docs/authorization.md), [cloud preparation](docs/cloud-preparation.md), [external trigger](docs/external-trigger.md), [migration and ordered rollout](docs/migration-and-rollout.md), [failure reporting](docs/failures.md) and [Free limits](docs/free-limits.md). The original attachment is preserved in docs/master-prompt.md; newer instructions in AGENTS.md override its old state/monitoring design.

```sh
python -m pip install -e .
easybosnian history
easybosnian run --mode verify
easybosnian run --mode preview
```

Routine or manually missed-start publication uses workflow_dispatch mode=daily in preparation.yml. Do not start daily while reviewing the branch or until migration and Worker deployment are complete. No paid fallback or automatic catch-up exists.

Manual daily reruns now offer **same_words** (retain theme/words, fresh text/caption/images and palette/layout choices), **same_theme** (same theme, three different words), **new** (new theme and words), and **custom** (your theme/words with fresh text/images). The default scheduled choice is new. Once fresh cards render, Instagram and Facebook remove only known same-date content before replacing it; confirmed manually deleted items are skipped. Buffer cannot delete published TikTok posts. Remove earlier versions manually if desired; TikTok reruns are not blocked by a deletion confirmation. See [manual reruns](docs/manual-reruns.md) for credentials, limits and rollout.

The previous eight card treatments are retained at the user's request. Preparation selects a layout independently per card and measures fit before writing a concise photorealistic scene prompt. Body fonts still step down at 160/240 characters (44/38/34 px) without truncation.

Pitanje dana varies objective Bosnian quizzes with two to four choices, including yes/no. The shared approved palette matches the theme and scene materials; captions never refer to removed posts or corrections. Pillow uses consistent paragraph baselines while preserving the previous layouts and dynamic font sizes.

Pillow keeps the approved layout placements, with balanced paragraph line breaks, consistent baselines, point-size-based leading and left alignment. It preserves exact reviewed wording and diacritics, avoids tiny orphan lines without adding extra lines, and measures full accented glyph bounds. Dynamic 44/38/34 px body sizing, PRIMJER hierarchy, panel accents and fit/contrast rejection remain.

Every newly prepared caption ends with a fresh contextual Bosnian invitation to learn on EasyBosnian, then easybosnian.com on its own final line. The closing sentence must fit the theme without leaking the quiz answer; it is generated each time, not a fixed slogan. Existing saved posts/content are unchanged.

Manual content choices are new, same_theme, same_words (same theme/words, fresh copy/images and palette/layout choices), and custom (theme/three words; blank fields reuse today, fresh text even with defaults). See docs/manual-reruns.md.

One persistent shared difficulty starts at A2. Change it through [the difficulty workflow](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/configure-level.yml) for future 05:00 runs and manual preparation. It writes only data/preparation-settings.json. same_words retains word difficulty while regenerating copy and design; new ChatGPT-selected words use the chosen level. Retained words keep their individual difficulty when rewritten. Each custom word can be kept, entered or delegated; a changed theme delegates keep-today slots, while a thematically incompatible entered word is replaced at the shared level after private review. Standard GitHub forms show all custom controls, which apply only to custom.

Visual quiz treatment B places the question above the complete photo and choices below it in both posts and Stories.

Development tests install the optional test dependencies with `python -m pip install -e ".[test]"`. CI parses every workflow YAML file as well as testing the content/renderer contracts, so malformed menu descriptions fail validation. Production publishing does not install the test-only YAML parser.
