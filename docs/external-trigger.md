# External daily trigger

The existing Worker easybosnian-daily-tifah-v1 starts only TifahEfendijaM/easybosnian-daily-uploads at **05:00 Europe/Sarajevo**. Its one cron is `0 3,4 * * *` (UTC). The handler converts controller.scheduledTime to Sarajevo and dispatches only intended local 05:00, selecting 03:00 UTC in summer or 04:00 UTC in winter, including transition days and delayed delivery. There is no watchdog cron or GitHub schedule.

[Cloudflare documents](https://developers.cloudflare.com/workers/configuration/cron-triggers/) that cron changes can take up to 15 minutes to propagate. Finish a same-day clock deployment at least 20 minutes before the requested slot; if that margin is missed, explicitly target the next day. A Git commit does not deploy this Worker. Only an actual Wrangler deployment updates its live bundle and registered cron. No extra retry/catch-up trigger is added.

On October 3 the 12:30 clock was uploaded at 12:24:49 Sarajevo and registered at 12:24:56, less than six minutes before the slot. The active deployed version and downloaded bundle matched that clock. Cloudflare's scheduled-event history contained the earlier 12:00 event but no 12:30 event, and D1 contained no dispatch claim. Propagation delay is the likely explanation, not a proven provider root cause. No daily run was dispatched manually.

Before contacting GitHub, D1 atomically inserts the date into preparation_dispatches. Duplicate cron deliveries and failed/uncertain/crash-interrupted claims cannot send another scheduled request. This protects only launch delivery, not publication. There is no automatic retry or missing-run alert.

The dedicated Worker-only GITHUB_DISPATCH_TOKEN is a fine-grained PAT restricted to this exact repository, Actions read/write and Metadata read only, expiring 2027-10-03. The Worker checks exact private repository identity and main, then sends:

```http
POST https://api.github.com/repos/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml/dispatches
```

```json
{"ref":"main","inputs":{"mode":"daily","batch_target":"none"}}
```

Headers retain Bearer authentication, Accept application/vnd.github+json, project User-Agent, Content-Type application/json and GitHub API version 2022-11-28. Only clock/gate decisions and status/mode are logged; credentials, content and provider response bodies are excluded. The gate log occurs before either inactive-time or disabled-start return, so an invoked but skipped event can be distinguished from no invocation. Scheduled failures also produce a generic error log without provider details. Require HTTP 204; non-204 or network failure throws and preserves the claim without retry. redirect:manual remains because Workers does not support redirect:error, and credentials must not follow a redirect.

POST /v1/scheduler/verify is admin-protected and sends mode=verify. It cannot prepare, publish or consume a daily claim. GET /v1/scheduler/status exposes only private recent cron records. For a separately requested dispatch-only check, scripts/test_external_trigger.py starts an actual verify run. The present migration uses main’s protected read-only connection checks and sends no workflow dispatch. A manual verify does not prove future cron delivery or publication.

The workflow on main must accept daily **before** deploying/arming the new Worker, or GitHub rejects the input with 422. For migration 0005, follow multiple-batches.md: merge first, pause live publishing during the storage cutover, preserve the existing cron claim and dispatch clock, then restore the previous publishing switch after verification. The earlier state-machine removal and unused-secret cleanup are documented separately in migration-and-rollout.md.

## Clock consistency and deployment

Before every deploy through scripts/cloudflare_deploy.py, validate_schedule compares the Worker hour/minute gate to both the real ignored wrangler.toml and committed wrangler.example.toml. It derives the summer/winter UTC candidates from Europe/Sarajevo and refuses any mismatch before invoking Wrangler. Run it explicitly before a direct Wrangler deploy too. CI checks the committed example; only the deployment host can check its ignored real config.

```sh
python -c "import sys; sys.path.insert(0, 'scripts'); from cloudflare_deploy import validate_schedule; validate_schedule()"
# Then use the existing guarded deployment procedure; read back the live cron and version.
```

CI deployment would remove the manual merge/deploy gap, but needs a separate least-privilege Cloudflare deploy credential, protected environment and a config assembled from this project's resource IDs. It must run after successful checks, perform the same clock check, and verify the live bundle/crons after deployment. Do not reuse the Worker-only GitHub dispatch token or desktop OAuth session. CI deployment is not enabled by this change; no new access was requested.

For the multiple-batch change, main must accept the new none batch_target choice before deploying this Worker revision; otherwise GitHub rejects dispatch with 422. Merge and require checks first, then deploy the same Worker and verify its live bundle/cron without sending a daily test. The clock and per-date claim remain unchanged. Manual form runs default to latest; the Worker explicitly chooses none so each morning creates the new day’s batch. Migration 0005 is required for multiple independent batches. See multiple-batches.md.
