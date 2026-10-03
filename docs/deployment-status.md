# Deployment status — 3 October 2026

The history-only design was implemented on simplify-daily-pipeline, reviewed through a full diff and card previews, and merged in [PR #9](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/pull/9). Main accepted verify/preview/daily before the Worker changed its dispatch mode.

## Applied rollout

- The external start stayed disabled during the transition, with no active content workflow.
- The guarded cleanup removed 18 artwork keys for the explicitly rejected October 3 batch. It did not delete social posts.
- Recorded D1 migrations created history, excluded the exact rejected package, cleared only October 3's cron claim and dropped the legacy batches/reservations/generations/settings/alerts/events tables. No other content rows existed, so active history is now empty.
- The new Worker was deployed disabled against the same existing database and KV.
- The protected [verify run](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/37115321418) succeeded: private infrastructure and the dedicated ChatGPT workspace/sign-in were checked, refreshed cloud credentials persisted, and the render/publish step was skipped.
- The Worker was armed, with the sole cron 0 10,11 * * * and scheduledTime gating for **12:00 Europe/Sarajevo**. Storage identity and private history/claim read-back passed. No watchdog or GitHub cron remains.

[Main validation](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/37115253792) passed all 46 Python and 11 Worker tests and the protected infrastructure check. The original master prompt and transparent watermark are unchanged.

## Posting and monitoring

DAILY_POSTING_ENABLED, FACEBOOK_POSTING_ENABLED, TIKTOK_POSTING_ENABLED and INSTAGRAM_STORIES_ENABLED are enabled. One daily job researches replacement content, saves today's history, persists credentials, renders the cards and attempts Instagram, Facebook and Buffer TikTok. Instagram image Stories follow confirmed feed publication. No awake Mac is required.

No new batch was prepared or published during this rollout. October 3's noon passed while the external start was paused; there is no automatic catch-up or retry. The next scheduled start is **4 October 2026 at 12:00 Europe/Sarajevo**. A deliberate manual run uses the normal daily mode. Successful verification is connection evidence, not proof of future publication.

Stored obsolete monitoring secrets/variables are removed after deployment. Revoke old Healthchecks checks/ping URLs and the notification-only PAT separately at their providers; secret deletion does not revoke them. [Authorization](authorization.md) lists all names. No missing-run monitor remains; publication duplicates after ambiguous responses or manual daily reruns are accepted by the user.

Existing isolated resources remain: Worker easybosnian-daily-tifah-v1, account a480e6f6c5bb20c20f96afb031962c40, D1 d40605f4-ff3a-4247-9f52-48a22f839d0d and KV da9fd7f503c5402ea28ac7ad304002b5. No new resource, paid fallback or desktop sign-in copy was created.
