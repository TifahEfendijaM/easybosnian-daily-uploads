# Successful-run reports

Every successful daily publication, including manual reruns, creates an approved report visible directly in the GitHub run Summary, including when the repository is public. No email setup or sending credential is needed.

## Where to read it

1. Open [EasyBosnian workflow runs](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml).
2. Select the successful daily run. On its **Summary** page, scroll to **EasyBosnian — successful-run report**. The theme, difficulty and palette appear first, then the three exact FLUX prompts in copyable code blocks and confirmed publication links/statuses.
3. For a saved copy on private-repository runs, download the **easybosnian-daily-RUN_ID** artifact at the bottom of the page. Inside its batch-ID folder, open success-report.md, success-report.html or success-report.json. Artifacts last seven days. The Summary remains with the workflow run until that run is deleted under GitHub's retention policy; it does not depend on artifact expiry.

Public-repository run summaries are public by request. Downloadable artifacts remain restricted to private-repository runs. On public runs, approved report copies are retained in authenticated Worker storage for 14 days; fetch them locally with `python -m easybosnian.run_reports fetch --run-id ID` using the existing project environment. Reports never expose credentials, private answer keys, source-review notes or raw model output. No public Worker route or new database table is added.

## Exact-run content and limits

A small local, whitelisted report-source.json captures the exact rendering input before generation; reporting never rereads a history row that a later replacement could have overwritten. This is a run artifact, not an immutable package or publication state machine. The report binds that snapshot to the exact prepared batch ID/date, GitHub run and its confirmed publication results.

Verify and preview do not create publication-success reports. A failed or partial publication creates no success report; its existing failure summary/artifacts/issues remain. Cleanup warnings may accompany a successful replacement; the report notes that old content may remain. Links describe confirmation at completion, not permanent availability after replacement or Story expiry.

Report errors are ancillary warnings and do not undo, block or retry completed publication. No new schedule, retry, email service, credentials or paid dependency is introduced. A completely missing run still produces no report or notification, as previously agreed.

The first morning report, from the October 4 run before this feature existed, is available as [a private backfilled report](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/issues/38). Future reports use the run Summary directly; this is not a new per-run issue or alert mechanism.

Successful all_today runs also show whether earlier same-date history removal failed; a warning means some earlier themes/words may still be in history. Cleanup counts appear in the platform summary. Unsupported Facebook Stories/photos and TikTok cleanup stays manual. Reports never expose erased content, quiz answers or credentials.

Hybrid runs distinguish the fallback preparation palette from the final rendered per-card palettes and actual free/default/separate-photo rendering, approved card design ID and per-block styles (including italic_photo, italic_photo_fade or italic_footer examples) and validated per-block typography. Safe composition coordinates are in image-placement-result.json; no raw visual-agent prose or private quiz review appears in the report.

Every card records two independent sources: **Layout source** and **Palette source**, each ChatGPT or fallback with its fixed reason. A ChatGPT layout can use the preparation fallback palette; a default layout can keep ChatGPT’s approved palette. Matching palette IDs do not establish source. Unavailable review, uncertain confidence and measured layout rejection remain distinct diagnostics; missing/unapproved palettes and palette contrast failures have separate reasons. The heading says final rendered palette rather than claiming every final palette was photo-reviewed. The ordinary run Summary includes this even when a platform fails; successful reports include the same information in Markdown/HTML/JSON. Older runs without a reason are labelled unrecorded rather than guessed; palette provenance absent from an older artifact is explicitly unknown. Markdown, HTML and JSON copies carry the same separate sources. The legacy outcome field describes layout only.

Each image now has a readable description of the applied design: its independently selected palette, photo layout, category treatment, title/example tones, body/answer/example styles, badge shapes and approved block placement/typography. These describe recorded final rendering choices, not invented model reasoning. The ordinary run Summary also shows the exact locally captured FLUX prompts and these descriptions when a run fails or partially publishes. If image review never completed, prompts remain visible and design decisions are explicitly unavailable. Invalid or mismatched reporting metadata is omitted with a warning; no raw model prose or private answers are included.

The ordinary public run Summary includes the full redacted failure report even before generation, or alongside partially successful publication: failed stage, actual safe error and codes, publication state, run link and next step. It is not replaced with a generic protected-report notice. Credentials remain redacted; raw provider/model traces, private drafts and answer keys stay excluded. Recognised saved FLUX error descriptions add fixed content-safety, free-allocation or capacity explanations without exposing the original provider prose or making another inference request.
