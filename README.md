# EasyBosnian daily uploads

Private project: **TifahEfendijaM/easybosnian-daily-uploads**. All project history and state are fresh and isolated. No other user repository is used.

Every day, a tool-enabled preparation task researches and reviews one new theme and three new Bosnian words, then saves an immutable JSON package. GitHub Actions asks Cloudflare Workers AI / FLUX.1 Schnell for three text-free backgrounds, adds exact reviewed lettering and the original transparent logo with Pillow, and publishes a three-image Instagram carousel through Instagram Login.

## Current authorized schedule

- Preparation: **05:00 daily, Europe/Sarajevo**, started once by the existing Cloudflare Worker through GitHub's dispatch API. GitHub's schedule block is removed; DST is handled automatically.
- Pipeline: **immediately after successful preparation**; no fixed publication cron.
- No scheduled retry. The existing Cloudflare Worker now also starts preparation at 05:00; its separate 06:59 check only reports failures. See [external-trigger setup and manual testing](docs/external-trigger.md).
- The user waived the original prompt's unpublished-preview and separate live-test gates on 2026-10-02. Daily posting is authorized. The user then deferred Healthchecks until after Instagram works; verified GitHub issue reporting is used during that phase.

Both preparation and publishing run on private GitHub cloud runners, independently of the Mac, after the dedicated cloud ChatGPT sign-in is verified. Preparation uses the existing ChatGPT subscription through the official Codex CLI, with no paid API key. Its serialized workflow restores and persists refreshed credentials in private secrets. A connection check proves ChatGPT access, private history and GitHub write/read-back without preparing a batch or publishing. The first real reviewed package save/read-back enables Cloudflare's publication gate. Preparation cron and runner queues can be delayed. Publication starts immediately after successful preparation, including credential persistence; there is no artificial wait. If today's reviewed package is missing or mismatched, the pipeline fails clearly without publishing stale text. The publisher checks the handed-off date and immutable package hash and checks out main to retrieve the newer reviewed queue commit. The daily run contains preparation and publication jobs. No retry is dispatched.

## Architecture and privacy

Cloudflare D1 holds all reserved/used themes, word equivalents, immutable packages and publication state. Atomic unique reservations check both queued and historical content. The preparation task also performs semantic checks for renamed themes and close variants; deterministic normalization cannot prove semantic novelty by itself. Reservations never expire or reset automatically.

Cloudflare KV stores images for 14 days, keeping storage bounded. Only final JPEGs with random 256-bit URLs are public; there is no public listing, history or JSON endpoint. Original/generated backgrounds are private. Final cards are 1080×1350 and are shared with Instagram, Facebook and the authorized Buffer TikTok publisher. The optional vertical export is disabled.

All 11 approved palettes are in `data/design-palettes.json`; all eight layouts are in `data/design-layouts.json`. Inter regular, semibold and bold, plus its license, are bundled. ChatGPT selects palette/layout metadata for Pillow, then writes short natural FLUX scene prompts with ordinary colour names, lighting and optional broad composition. FLUX prompts omit hex codes, coordinates and text/UI/box descriptions; they always forbid text, lettering and logos. Quiz backgrounds still avoid answer clues. Pillow uses measured glyph bounds, content-sized panels and the specified 44/38/34 px density tiers. It rejects overlong copy rather than truncating or dropping diacritics. Already reserved packages and cached artwork are reused exactly; the simplified prompting applies to new batches.

Instagram credentials are stored only in GitHub Actions secrets and protected authorization tooling. The pipeline verifies `@easy_bosnian`, refreshes unexpired long-lived tokens around day 40, and persists replacements to GitHub secrets using a token restricted to this repository. No Facebook Page link is needed. Facebook authorization is independent; its exact Easy Bosnian Page and published Meta app are verified, and daily Facebook publishing is enabled.

Publication intent is saved before the publish request. Completed backgrounds, cards, child containers and carousel container are reused. After a timeout or uncertain response, rerunning cannot repost; `reconcile` checks recent account media and verifies the actual expected caption, three children and permalink. Green CI alone never means publication. An ambiguous or absent match requires manual inspection.

## Setup and operation

See [authorization guide](docs/authorization.md), [cloud preparation](docs/cloud-preparation.md), [failure reporting](docs/failures.md), [free limits](docs/free-limits.md), and [daily preparation instructions](docs/preparation-task.md). The attached original prompt is preserved in `docs/master-prompt.md`; `AGENTS.md` records the user's later authoritative changes.

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

## Facebook and TikTok publishing

Facebook posts the same three cards as a Page photo post, with independent intents, photo IDs, exact caption and permalink verification. The user now wants native tappable Instagram post reshares; these require manual action in Instagram, so standalone image Stories are disabled. TikTok Stories also require manual upload with the current Buffer integration. Daily results state both limitations explicitly; feed publishers continue independently. Highlight additions remain manual.

TikTok uses the user's **Free Buffer account** and its verified **@easy.bosnian** connection. The pipeline submits the same three JPEGs with automatic publishing, saves its submission intent and Buffer post ID, then checks that ID for up to four minutes. It reports success only when Buffer confirms automatic/sent status, the expected account, caption, three ordered asset identities and an actual TikTok permalink. This is Buffer-confirmed publication, not an independent TikTok API inspection. The API key is stored only in this private repository's secrets and has account reading and post reading/writing permissions. Renew it before **2027-10-03**. Buffer handles the underlying TikTok connection; revoked permissions still require reconnecting. No TikTok developer app, privacy change, music selection, paid plan or scheduled retry is used. An unknown submission outcome stops safely; `easybosnian tiktok --mode reconcile --date YYYY-MM-DD` performs read-only reconciliation. The first actual daily TikTok post remains unverified until a live run succeeds.

If a scheduled trigger is missing, manual preparation dispatch defaults to verify. The explicit recover_today mode prepares and publishes today with the same batch/hash checks and immediate handoff; select it deliberately under the existing daily publication authorization; routine connection checks still cannot publish. It is not a timer or automatic retry.
