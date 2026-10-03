# Review status — 2026-10-03

The simplification is prepared on branch **simplify-daily-pipeline** for full-diff review. It changes the design to a single history table and one verify/preview/daily workflow, removes the publication/reservation/queue/monitoring machinery and improves Pillow text panels.

Before this branch started, the user's noon reschedule began with a guarded deployment of the existing Worker at 12:00 daily but **PREPARATION_DISPATCH_ENABLED=false** during today's cleanup. That paused Worker still uses the legacy content API/recover_today mode and still contains reporting cron slots. No branch migration or new Worker is deployed during review. Today's old database record is still present; the branch removes its queue entry and migration 0003 excludes its exact rejected content. Therefore no fresh scheduled publication occurs while the start remains paused.

Existing credentials, original watermark, GitHub main and other repositories are preserved. Existing Instagram/Facebook/Buffer setup is authorized. No new FLUX call, history mutation or social publication is needed to review the renderer or code. Card previews use explicitly unreviewed fixture content/drawn backgrounds.

After review, follow migration-and-rollout.md in order: merge repository workflow first, clear rejected-date artwork, apply tracked D1 migrations, deploy new Worker disabled, verify connections, then arm noon cron. No automatic catch-up is dispatched if noon has passed. A deliberate normal daily dispatch is the only manual missed-start route.
