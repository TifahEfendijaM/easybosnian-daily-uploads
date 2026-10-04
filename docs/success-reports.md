# Successful-run reports

Every successful daily publication, including manual reruns, creates a private report visible directly on GitHub. No email setup or sending credential is needed.

## Where to read it

1. Open [EasyBosnian workflow runs](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml).
2. Select the successful daily run. On its **Summary** page, scroll to **EasyBosnian — successful-run report**. The theme, difficulty and palette appear first, then the three exact FLUX prompts in copyable code blocks and confirmed publication links/statuses.
3. For a saved copy, download the **easybosnian-daily-RUN_ID** artifact at the bottom of the page. Inside its batch-ID folder, open success-report.md, success-report.html or success-report.json. Artifacts last seven days. The Summary remains with the workflow run until that run is deleted under GitHub's retention policy; it does not depend on artifact expiry.

Repository access is required, including for anyone you share the run link with. Reports never expose credentials, private answer keys, source-review notes or raw model output. No public Worker route or new database table is added.

## Exact-run content and limits

A small local, whitelisted report-source.json captures the exact rendering input before generation; reporting never rereads a history row that a later replacement could have overwritten. This is a run artifact, not an immutable package or publication state machine. The report binds that snapshot to the exact prepared batch ID/date, GitHub run and its confirmed publication results.

Verify and preview do not create publication-success reports. A failed or partial publication creates no success report; its existing failure summary/artifacts/issues remain. Cleanup warnings may accompany a successful replacement; the report notes that old content may remain. Links describe confirmation at completion, not permanent availability after replacement or Story expiry.

Report errors are ancillary warnings and do not undo, block or retry completed publication. No new schedule, retry, email service, credentials or paid dependency is introduced. A completely missing run still produces no report or notification, as previously agreed.

The first morning report, from the October 4 run before this feature existed, is available as [a private backfilled report](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/issues/38). Future reports use the run Summary directly; this is not a new per-run issue or alert mechanism.

Successful all_today runs also show whether earlier same-date history removal failed; a warning means some earlier themes/words may still be in history. Cleanup counts appear in the platform summary. Unsupported Facebook Stories/photos and TikTok cleanup stays manual. Reports never expose erased content, quiz answers or credentials.

Hybrid runs distinguish the fallback preparation palette from the photo-reviewed final palette and actual free/default/separate-photo rendering, approved card design ID and per-block styles (including italic_photo or italic_footer examples). Safe composition coordinates are in image-placement-result.json; no raw visual-agent prose or private quiz review appears in the report.
