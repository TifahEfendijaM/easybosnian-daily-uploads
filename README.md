# EasyBosnian daily uploads

Private repository **TifahEfendijaM/easybosnian-daily-uploads**. The existing Cloudflare Worker starts one GitHub workflow at **12:00 daily Europe/Sarajevo**. The clock handles daylight saving automatically. GitHub has no schedule trigger, and there is no automatic retry or missing-run monitor.

One job follows a straight path: a GPT agent through the existing ChatGPT subscription researches and reviews content → the wrapper saves today's Cloudflare history row → refreshed cloud credentials are persisted privately → Pillow renders three cards using Free FLUX backgrounds → Instagram, Facebook and Buffer TikTok publish → Instagram uploads the same cards as image Stories. Publication starts immediately after preparation. No awake Mac or paid OpenAI API is needed.

## Three modes

| Mode | Content | Images | Posting |
|---|---|---|---|
| verify (default) | Reads history and verifies connections/workspace only | None | None |
| preview | Reuses today's row, or researches/saves it if absent | Renders private cards | None |
| daily | Always researches and overwrites today's content | Renders replacement cards | All enabled platforms |

The user chose complete same-date overwrite. A daily run after a preview prepares replacement content rather than posting that preview's exact cards. Earlier same-day themes/words are removed from future novelty checks. Other dates' history remains. Previewed content counts toward history until replaced, even if never posted.

**DAILY_POSTING_ENABLED is the live kill switch.** Every live entry point checks it independently of event type. verify and preview do not depend on it. Separate FACEBOOK_POSTING_ENABLED, TIKTOK_POSTING_ENABLED and INSTAGRAM_STORIES_ENABLED switches control those publishers. PREPARATION_DISPATCH_ENABLED controls only Cloudflare starts.

## History and validation

D1 history is the single source of truth: one date, theme, three words with equivalence keys, and the complete reviewed day's content. There is no queue directory, content commit/read-back, package hash, reservation ledger or publication state. Theme/word comparisons still check aliases and normalized spelling, while GPT performs semantic review and source research. Quiz answers remain private. Schema, measured text fit, contrast and diacritics checks reject invalid content without truncation.

Pillow renders exact text and the original transparent watermark onto 1080×1350 cards. Body sizes are 44/38/34 px at 160/240-character boundaries. Licensed Inter, semibold headings, rounded panels, inset accent lines and a PRIMJER label give the definition/example a clearer hierarchy. GPT selects one shared palette and per-card layouts from the approved catalogs. FLUX receives short natural scene descriptions, plain colour names and at most one broad framing direction; Pillow handles text and branding.

KV images expire after 14 days. Only final card/Story JPEGs receive random public URLs for social platforms to fetch. Shared backgrounds are cached, and a reviewed content replacement invalidates that date's caches. Instagram Stories pad the actual cards to 1080×1920; Highlights and TikTok Stories require manual action.

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
