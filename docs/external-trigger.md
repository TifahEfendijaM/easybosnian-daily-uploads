# External daily trigger

The existing Worker easybosnian-daily-tifah-v1 starts only TifahEfendijaM/easybosnian-daily-uploads at **12:00 Europe/Sarajevo**. Its one cron is `0 10,11 * * *` (UTC). The handler converts controller.scheduledTime to Sarajevo and dispatches only intended local noon, selecting 10:00 UTC in summer or 11:00 in winter, including transition days and delayed delivery. There is no watchdog cron or GitHub schedule.

Before contacting GitHub, D1 atomically inserts the date into preparation_dispatches. Duplicate cron deliveries and failed/uncertain/crash-interrupted claims cannot send another scheduled request. This protects only launch delivery, not publication. There is no automatic retry or missing-run alert.

The dedicated Worker-only GITHUB_DISPATCH_TOKEN is a fine-grained PAT restricted to this exact repository, Actions read/write and Metadata read only, expiring 2027-10-03. The Worker checks exact private repository identity and main, then sends:

```http
POST https://api.github.com/repos/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml/dispatches
```

```json
{"ref":"main","inputs":{"mode":"daily"}}
```

Headers retain Bearer authentication, Accept application/vnd.github+json, project User-Agent, Content-Type application/json and GitHub API version 2022-11-28. Only status/mode are logged. Require HTTP 204; non-204 or network failure throws and preserves the claim without retry. redirect:manual remains because Workers does not support redirect:error, and credentials must not follow a redirect.

POST /v1/scheduler/verify is admin-protected and sends mode=verify. It cannot prepare, publish or consume a daily claim. GET /v1/scheduler/status exposes only private recent cron records. Run scripts/test_external_trigger.py after the migration/deployment sequence and require the actual verify run to pass. A manual verify does not prove future cron delivery or publication.

The workflow on main must accept daily **before** deploying/arming the new Worker, or GitHub rejects the input with 422. Keep PREPARATION_DISPATCH_ENABLED false during rollout. Exact commands, migration effects and unused-secret cleanup are in migration-and-rollout.md.
