# EasyBosnian daily uploads

Private project: **TifahEfendijaM/easybosnian-daily-uploads**. All project history and state are fresh and isolated. No other user repository is used.

Every day, a tool-enabled preparation task researches and reviews one new theme and three new Bosnian words, then saves an immutable JSON package. GitHub Actions asks Cloudflare Workers AI / FLUX.1 Schnell for three text-free backgrounds, adds exact reviewed lettering and the original transparent logo with Pillow, and publishes a three-image Instagram carousel through Instagram Login.

## Current authorized schedule

- Preparation: **17:00 daily, Europe/Sarajevo**.
- Pipeline: **17:10 daily, Europe/Sarajevo**, including daylight saving changes.
- No scheduled retry. A monitoring-only Cloudflare check runs at 17:50; it cannot generate or publish.
- The user waived the original prompt's unpublished-preview and separate live-test gates on 2026-10-02. Daily posting is authorized. Setup still requires working provider credentials and monitoring.

The preparation automation is local to this chat and needs the computer awake and the app running. GitHub Actions and Cloudflare run independently in the cloud. A saved automation does not prove successful GitHub writing: setup verifies an actual reviewed JSON save and read-back before activation. Cron timing can be delayed; ten minutes is not guaranteed. If today's reviewed package is missing or mismatched, the pipeline fails clearly without publishing stale text. A late package is kept for a deliberate run; no retry is dispatched.

## Architecture and privacy

Cloudflare D1 holds all reserved/used themes, word equivalents, immutable packages and publication state. Atomic unique reservations check both queued and historical content. The preparation task also performs semantic checks for renamed themes and close variants; deterministic normalization cannot prove semantic novelty by itself. Reservations never expire or reset automatically.

Cloudflare KV stores images for 14 days, keeping storage bounded. Only final JPEGs with random 256-bit URLs are public; there is no public listing, history or JSON endpoint. Original/generated backgrounds are private. Final cards are 1080×1350. The renderer also supports 1080×1920 exports, without TikTok posting.

All 11 approved palettes are in `data/design-palettes.json`; all eight layouts are in `data/design-layouts.json`. Inter regular, semibold and bold, plus its license, are bundled. Every background prompt is tied to the palette and card layout. Pillow uses measured glyph bounds, content-sized panels and the specified 44/38/34 px density tiers. It rejects overlong copy rather than truncating or dropping diacritics.

Instagram credentials are stored only in GitHub Actions secrets and protected authorization tooling. The pipeline verifies `@easy_bosnian`, refreshes unexpired long-lived tokens around day 40, and persists replacements to GitHub secrets using a token restricted to this repository. No Facebook Page link is needed. Facebook authorization is independent and deferred until Instagram works.

Publication intent is saved before the publish request. Completed backgrounds, cards, child containers and carousel container are reused. After a timeout or uncertain response, rerunning cannot repost; `reconcile` checks recent account media and verifies the actual expected caption, three children and permalink. Green CI alone never means publication. An ambiguous or absent match requires manual inspection.

## Setup and operation

See [authorization guide](docs/authorization.md), [failure reporting](docs/failures.md), [free limits](docs/free-limits.md), and [daily preparation instructions](docs/preparation-task.md). The attached original prompt is preserved in `docs/master-prompt.md`; `AGENTS.md` records the user's later authoritative changes.

The latest verified setup progress and remaining authorizations are recorded in [deployment status](docs/deployment-status.md).

Install Python 3.11+ and `python -m pip install -e .`. The local setup uses the bundled runtime and a virtual environment outside this repository. Credentials are entered privately through provider flows or hidden local prompts, never through chat.

```text
easybosnian history
easybosnian prepare build/preparation/YYYY-MM-DD.json
easybosnian pipeline --mode live --date YYYY-MM-DD
easybosnian pipeline --mode reconcile --date YYYY-MM-DD
easybosnian activation disable-daily
```

The `prepare` command validates schema, answer leakage, history keys and actual text fit; reserves the package in Cloudflare; writes only this repository's queue; and reads it back. All JSON in `queue/` is private, including quiz answers. An interrupted queue save resumes the same date/hash. Do not edit a reserved package behind the pipeline's back.

Code checks: `python -m unittest discover -s tests -v` and `node --test cloudflare/worker.test.mjs`. These test rendering, normalization, answer leakage, repository boundaries, publication verification and uncertainty handling. They do not publish or invoke FLUX.

## Later phases

Facebook: select the exact EasyBosnian Page through independent Pages authorization, store its Page ID/token separately, verify the Page identity and then add a publisher with separate publication state. No Facebook posting is enabled in this version.

TikTok: research is documented in `docs/authorization.md`. Public unattended posting is not promised; official audit and creator-control requirements restrict internal one-account utilities. No TikTok API publisher or paid service is configured.
