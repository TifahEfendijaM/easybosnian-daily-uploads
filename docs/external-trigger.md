# External daily preparation trigger

The existing Worker `easybosnian-daily-tifah-v1` starts the private repository `TifahEfendijaM/easybosnian-daily-uploads` at **05:00 Europe/Sarajevo**. GitHub still runs ChatGPT preparation and immediate reusable publication; its own `schedule` block is removed. No paid service, separate Worker or scheduled retry is added. Initial setup and successful manual verification are required before considering this active.

## Clock and request

Cloudflare cron is UTC. `0 3,4 * * *` invokes the same handler at both candidate hours. `Intl.DateTimeFormat` converts `controller.scheduledTime` to Europe/Sarajevo; only local 05:00 sends a request. This selects 03:00 UTC in summer and 04:00 UTC in winter, including transition dates. The handler uses the intended event time so a delivery delay does not silently skip that day's event. Existing monitoring remains at 06:59 Sarajevo.

The Worker first verifies the exact private GitHub repository and default branch main. It sends one request to:

```text
POST https://api.github.com/repos/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml/dispatches
```

```json
{"ref":"main","inputs":{"mode":"recover_today"}}
```

Headers include the Worker secret as Bearer authorization, `Accept: application/vnd.github+json`, a project User-Agent, Content-Type and `X-GitHub-Api-Version: 2022-11-28`. Run details are not requested, retaining the requested 204 contract. GitHub's February 2026 update documents 204 when `return_run_details` is omitted. The response status is logged; any non-204 throws. Logs never contain the token, authorization headers or API response body. Observability is enabled on the existing Free Worker.

Before contacting GitHub, D1 atomically claims the Sarajevo date. Accepted, failed, uncertain and crash-interrupted claims all prevent another scheduled request for that date. Network failures and ambiguous success/server responses retain uncertainty. There is no automatic resend. An operator must inspect GitHub and existing publication state before deliberate recovery. HTTP 204 means request acceptance, not a successful preparation or post.

## Repository-only token

Create a new fine-grained PAT under **TifahEfendijaM**, with **Only select repositories → easybosnian-daily-uploads**:

- Repository **Actions: Read and write**.
- Repository **Metadata: Read-only**, automatically included.
- No Contents, Secrets, Issues, account or organization permissions are required for this start token.

Store it only as Worker secret **GITHUB_DISPATCH_TOKEN**. Keep the existing NOTIFY_GITHUB_TOKEN separate. Choose an expiry and record renewal before it expires; a revoked/expired token stops automatic starts and is reported. Do not paste a token into chat, command arguments, a committed file or the patch.

## Setup and manual verification after approving the diff

The commands below are for the existing project and existing resources. Apply the reviewed repository changes and push them to private main before dispatch testing so the new run title and workflow gates are available. The actual wrangler.toml is ignored; both its reviewed configuration and the checked-in example must stay consistent.

This Mac uses the bundled Node/pnpm runtime; npx is not on its default path. Define this helper once in the terminal, then use the exact commands below from the Cloudflare directory:

```sh
easybosnian_wrangler() {
  PATH="/Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" \
    /Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm dlx wrangler@4.145.0 "$@"
}
cd /Users/fatih_efe/Documents/Codex/2026-10-02/read-the-entire-attached-easybosnian-master/work/easybosnian-daily-uploads/cloudflare
easybosnian_wrangler secret put GITHUB_DISPATCH_TOKEN --config wrangler.toml
```

Press Enter after the command, then paste the PAT into Wrangler's hidden secret prompt and submit it. This does not put the token into shell history.

Apply the additional table to this existing D1 database, then deploy with automatic dispatch temporarily disabled:

```sh
easybosnian_wrangler d1 migrations apply easybosnian-daily-tifah-v1 --remote --config wrangler.toml
easybosnian_wrangler deploy --config wrangler.toml --var PREPARATION_DISPATCH_ENABLED:false
```

The migrations are idempotent and preserve all current settings, packages, images and publication state. The existing guarded Python deployment helper now includes every migration for subsequent deployments.

In the repository directory, use the existing protected local credentials to manually exercise the deployed Worker with **verify only**:

```sh
cd /Users/fatih_efe/Documents/Codex/2026-10-02/read-the-entire-attached-easybosnian-master/work/easybosnian-daily-uploads
../.venv/bin/python scripts/test_external_trigger.py
```

This calls the admin-protected `/v1/scheduler/verify` endpoint. It uses the actual Worker-stored PAT and actual dispatch API, while forcing `mode=verify`. It cannot prepare/reserve content, publish or consume today's daily dispatch claim. Expect `github_status: 204`, then open this repository's Actions page and require the new **EasyBosnian preparation (verify)** run to finish successfully. The handoff step and publication job must be skipped. A 204 by itself is insufficient.

After verification succeeds, arm the committed true setting:

```sh
cd /Users/fatih_efe/Documents/Codex/2026-10-02/read-the-entire-attached-easybosnian-master/work/easybosnian-daily-uploads/cloudflare
easybosnian_wrangler deploy --config wrangler.toml
easybosnian_wrangler tail easybosnian-daily-tifah-v1 --config wrangler.toml --format pretty
```

Tail shows status logs without token contents. Cloudflare's dashboard also retains Workers Logs. Allow up to 15 minutes for cron changes to propagate. Read back the three cron expressions and enabled switch on the exact existing Worker. If verification fails, keep the dispatch switch false until the actual cause is fixed. Do not leave setup at the temporarily disabled stage and claim the daily launch is ready.

## Local tests and an optional real content test

```sh
cd /Users/fatih_efe/Documents/Codex/2026-10-02/read-the-entire-attached-easybosnian-master/work/easybosnian-daily-uploads
/Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --test cloudflare/worker.test.mjs
../.venv/bin/python -m unittest discover -s tests
```

The mocked Worker tests exercise both UTC candidates in summer, winter and on DST transitions, exact recover_today request headers/body, concurrent/duplicate delivery, missing/wrong credentials and every non-204/network failure with no resend. A SQLite migration test proves settings and date claims survive redeployment, and a preparation regression test confirms that a verified same-date batch emits no new handoff. These tests make no real GitHub or social publication request.

For a deliberate real content run after reviewing today's state, the existing authorized route remains:

```sh
gh workflow run preparation.yml --repo TifahEfendijaM/easybosnian-daily-uploads --ref main -f mode=recover_today
```

This can publish today's batch if it is unfinished. It directly tests content execution, not Cloudflare cron delivery, and is not needed just to verify the Worker PAT. Never use it as a blind retry after an uncertain response. For a confirmed already-published date, cloud preparation returns without another handoff. No real content test is run merely by applying this change.

## Duplicate publication checks and monitoring

The existing code was inspected: cloud_prepare.cloud_run checks the same-date reservation's verified Instagram state and returns “already verified published; preparation unchanged”; handoff.reviewed_result returns no outputs for that result. pipeline.pipeline also returns before artwork/publishing for verified Instagram state and refuses an existing uncertain publish_intent. Facebook returns when verified and blocks uncertain intents; Buffer uses the existing post ID instead of submitting again. Existing GitHub concurrency serializes preparation and publishers. These checks prevent blind reposting but do not constitute an exactly-once guarantee across every failure; an uncertain outcome needs read-only reconciliation. Also, the preparation early exit keys on Instagram verification, so another automatic invocation is not a repair mechanism for an incomplete Facebook/TikTok result.

Removing GitHub's schedule block is still recommended: one clock prevents redundant jobs and competing launches. No exact cron comparison is added to either job condition, and the remaining Python exact-cron check is removed. The 06:59 monitor now checks today's private dispatch record and recover_today workflow_dispatch runs, excluding verify-only tests. Dispatch acceptance without a matching run, a failed/uncertain claim, missing reviewed content or unverified Instagram publication is reported using the existing private issue route. The monitor never dispatches or retries. Check actual per-platform results before claiming publication succeeded.

Sources: [Cloudflare UTC cron and propagation](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [scheduledTime](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/), [GitHub dispatch token permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), [204 versus requested run details](https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids/), [Workers logging](https://developers.cloudflare.com/workers/observability/logs/workers-logs/).
