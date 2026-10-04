# EasyBosnian daily uploads

Private TifahEfendijaM/easybosnian-daily-uploads only. The existing Cloudflare Worker starts one GitHub Actions job at **05:00 Europe/Sarajevo**. It checks controller.scheduledTime against cron `0 3,4 * * *`, selecting the correct DST hour, then dispatches preparation.yml with mode=daily and batch_target=none. No GitHub schedule, automatic retry, catch-up, watchdog or Healthchecks.

A GPT agent through the existing ChatGPT subscription researches content against full private history → the trusted wrapper saves a reviewed batch → refreshed dedicated cloud credentials are persisted → Free Cloudflare FLUX backgrounds and Pillow produce three cards → Instagram, Facebook and Buffer TikTok publish independently → IG/FB image Stories follow their respective confirmed feed posts. No awake Mac or paid API.

## History and manual targets

Each history row has batch_id, date, created_at, theme, words/equivalents and reviewed content. Several batches may share a date. Latest is the newest complete saved batch by creation time/insertion order, including previews; editing it preserves that order. Legacy imported creation times are estimated from the available review timestamp or midnight UTC.

| batch_target | Behavior |
|---|---|
| latest (manual default) | Replace exactly the newest complete batch; keep its ID/date; attempt only its known latest IG feed/Stories and FB feed cleanup |
| none | Add a separate batch for the current Sarajevo date; preserve every existing batch/post and skip all cleanup |
| all_today | Add a replacement for the current Sarajevo date; after render, erase earlier same-date history/artwork and attempt all their supported known posts. Empty today never deletes yesterday. |

For any target choose same_words (same theme/words, fresh copy/design/images), same_theme (same theme, different words), new (new theme/words), or custom (entered theme/word/comparison/topic, or keep/delegate individual choices). none may use the latest batch as its selection source, including yesterday’s batch after midnight. Explicit reuse is permitted across copies; all ChatGPT-selected new terms still compare with every history batch. latest overwrites only its selected content; none retains its source. The 05:00 run uses none/new and always creates that morning’s batch.

Modes remain exactly verify, preview and daily. verify checks connections/workspace without preparing/rendering/publishing. latest preview reuses exact saved content; none/all_today preview researches/saves another independent private batch without cleanup. daily always researches fresh copy according to selection and publishes after persistence succeeds. Previewed content counts in history. Read [manual controls](docs/manual-reruns.md), [the brief Bosnian guide](docs/boss-guide-bs.md) and [migration/rollout](docs/multiple-batches.md).

## Publishing and limits

DAILY_POSTING_ENABLED is checked unconditionally by live entry points; verify/preview work while false. Platforms verify their exact accounts and perform immediate provider read-back. Cleanup is best effort and does not block replacement publishing. Only known IDs from the frozen selected batch scope are eligible; Instagram uses the separate linked-Page deletion credential, Facebook deletes feed posts only. Facebook Stories/backing photos and TikTok posts are manual. Latest cleanup never deletes all posts from a date; only explicit all_today targets every frozen same-date batch. Cleanup never follows a provider ID from outside its scope or retries a publish request. Ambiguous responses can still leave duplicate posts. Missing starts produce no alert, by the user’s choice.

Private/publication metadata, generation cache, cards, Stories and local artifacts use batch_id. Public image URLs remain random with 14-day expiry; history/answer keys are private. Content rows, known IDs and the cron claim are the only durable bookkeeping; no reservation, immutable package hash, intents, generation-state rows, queue commits, reconciliation or optimistic concurrency.

The credential-free Codex child keeps its stripped environment, workspace sandbox, structured ready/blocked contract and tracked-file diff check. It cannot publish or call protected APIs. The wrapper enforces schema, Bosnian spelling/diacritics, source/semantic review, quiz secrecy, measured text fit, shared difficulty and footer before saving. Never truncate text. Source review dates describe actual research, even when replacing an earlier content date. notify.failure retains build/failure.txt and opens a private GitHub issue with stage/date/publication status/run link; safe artifacts last seven days.

## Editorial and design

All visible copy is Bosnian. Quizzes have one objective answer and 2–4 options, including yes/no; images stay relevant and conceal only the unknown being tested. Znaš li? can cover practical facts, comparisons or topics. Eight approved feed treatments, eleven shared palettes, bundled Inter, PRIMJER hierarchy, accents and measured dynamic 44/38/34 px body fonts remain. Plan natural photographic scenes, then choose a complementary palette for Pillow; do not force unnatural colours into FLUX. Prompts are concise, photorealistic and layout-aware, without blank areas, coordinates or UI instructions.

Stories use B for word/lesson and visual naming quizzes, A for other quizzes. Visual naming also uses B on the regular quiz slide, with the question above the full photo. Other regular card layouts remain unchanged. New captions end with a fresh contextual Bosnian invitation and exactly `👉easybosnian.com` on their final line; never mention deleted/replaced posts.

One shared A1–C2 difficulty is changed through [configure-level.yml](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/configure-level.yml), separately from publication. It persists for future preparations; retained and compatible entered words keep their individual levels. No source/fit/secrecy checks are waived by custom input. See docs/difficulty-policy.md.

## Successful-run reports

Successful daily runs and reruns save a private report with the exact FLUX prompts, per-card layouts, palette, difficulty and confirmed publication links. Open [daily workflow runs](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml), select the completed run, then read **EasyBosnian — successful-run report** on its **Summary** page. The three prompts have copyable code blocks. Download Markdown/HTML/JSON copies under **Artifacts** for seven days. Public report metadata is captured from the rendering input within that run, so a later replacement cannot change its prompts. Report failure warns without affecting completed uploads. Verify and preview create no publication-success report. No email credential or extra setup is required. See [access and limits](docs/success-reports.md).

## Deployment

A merge alone does not deploy Cloudflare. Migration 0005 carries every existing content row and known ID into batch scopes, preserving ID insertion order and all cron claims. Apply it once through Wrangler; never replay migration 0003 or recover discarded packages. Legacy date-only reads remain available; ambiguous date-only writes/generation/publication access refuse to guess. New code uses explicit batch paths. Require checks, finish the protected maintenance sequence, read back live schema/bundle/clock and restore the existing kill switch. No automatic live test is dispatched. See [exact rollout and data limits](docs/multiple-batches.md).

New captions mention their actual lesson difficulty naturally in Bosnian prose, using a truthful range for mixed levels; retained unknown ratings stay unknown. The contextual website invitation remains last. all_today keeps unsupported/uncertain publication IDs for cleanup only; Facebook Stories/photos and TikTok posts still require manual removal. Preview never performs cleanup or erases history.
