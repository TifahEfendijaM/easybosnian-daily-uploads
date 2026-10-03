# Reviewed migration and deployment order

Work is on simplify-daily-pipeline. Review the full diff and rendered fixtures before applying production changes. The noon clock and existing credentials stay on the same Worker/resources. There is no reason to keep separate preparation/publication jobs: one job still preserves refreshed cloud credentials before rendering and live posting.

## What migration 0003 does

Creates **history(date, theme_json, words_json, content_json)**. It copies every existing batch's reviewed content, theme, words and equivalence metadata, except the user's explicitly rejected 2026-10-03 package with hash 759bd137b4b4ed33a37a7efdda952925ef345e8c31aa40c78f4754980e493f7a. That rejected row is discarded so today's normal daily run starts fresh. Only October 3's cron claim is cleared under that same explicit reset request; other cron claims stay intact.

Drops batches, reservations, generations, settings, alerts and events. This permanently removes publication/container/Story state, package hashes, revisions, generation intents, reservation keys, activation/monitoring flags, stored diagnostic events and alert deduplication. Returned IDs in old private GitHub artifacts and historical Git commits are not rewritten. Social posts are not deleted by this database migration. The one-time artwork cleanup removes only the rejected date's private/FLUX cache and public image URLs recorded in its old state. Other dates/resources stay untouched.

Apply migrations through Wrangler's recorded migration mechanism, **once**. Never manually replay migration 0003 on each deployment: it is a transition, not an automatic date reset. Legacy 0001/0002 remain solely as the migration chain for existing/fresh databases; runtime code never uses their removed tables after 0003.

## Exact ordered sequence

Use only this checkout. Keep the external start disabled until all steps pass. The old clock was already paused during review.

1. Push/review branch, then merge its repository changes to **main first**. Require the new preparation.yml on private main to list exactly verify/preview/daily. Its checks and publishing-kill-switch checks must pass. Do not deploy a Worker sending daily while main still accepts only verify/recover_today: GitHub returns 422.
2. Confirm no preparation/publishing run is active. Run the guarded one-time rejected-artwork cleanup **before** dropping the old batches table.
3. Apply D1 migrations. Existing content is copied, the rejected row excluded and old tables dropped.
4. Deploy the new Worker with its external start disabled. Check the exact existing D1/KV bindings and **only** cron `0 10,11 * * *`.
5. Run the protected Worker verify dispatch. Require the actual verify workflow to finish successfully with no history write, FLUX, rendering or publishing. It confirms protected infrastructure, cloud workspace and credential persistence.
6. Set the existing DAILY_POSTING_ENABLED variable true if routine publication is intended. Deploy/arm the same Worker with PREPARATION_DISPATCH_ENABLED=true, then read back the binding, cron, private history and per-date claim status.
7. Remove the obsolete credentials/variables below. No automatic content run or retry is dispatched. If noon has passed, today needs a deliberate normal daily dispatch; otherwise the noon cron starts it. Do not send a new verify test as evidence of actual posting.

Mac commands (existing bundled runtime):

```sh
cd /Users/fatih_efe/Documents/Codex/2026-10-02/read-the-entire-attached-easybosnian-master/work/easybosnian-daily-uploads
# After the reviewed repository branch has landed on main:
../.venv/bin/python scripts/clear_rejected_artwork.py
```

Define the existing-runtime Wrangler helper:

```sh
easybosnian_wrangler() {
  PATH="/Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" \
    /Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm dlx wrangler@4.145.0 "$@"
}
cd cloudflare
easybosnian_wrangler d1 migrations apply easybosnian-daily-tifah-v1 --remote --config wrangler.toml
easybosnian_wrangler deploy --config wrangler.toml --var PREPARATION_DISPATCH_ENABLED:false
cd ..
../.venv/bin/python scripts/test_external_trigger.py
# Require the actual verify workflow success before arming:
../.venv/bin/easybosnian activation enable-daily
cd cloudflare
easybosnian_wrangler deploy --config wrangler.toml
```

The ignored actual wrangler.toml must match the checked-in example with existing IDs: database d40605f4-ff3a-4247-9f52-48a22f839d0d and KV da9fd7f503c5402ea28ac7ad304002b5. Keep account a480e6f6c5bb20c20f96afb031962c40 and Worker easybosnian-daily-tifah-v1. No new resources or token are needed. Replace an expired start token only via the hidden `wrangler secret put GITHUB_DISPATCH_TOKEN --config wrangler.toml` prompt.

## Unused credential cleanup after deployment

```sh
# Run from the exact guarded repository checkout:
gh secret delete HC_PIPELINE_URL --repo TifahEfendijaM/easybosnian-daily-uploads
gh secret delete HC_PREPARATION_URL --repo TifahEfendijaM/easybosnian-daily-uploads
gh variable delete CLOUD_PREPARATION_ENABLED --repo TifahEfendijaM/easybosnian-daily-uploads
gh variable delete INSTAGRAM_STORY_MODE --repo TifahEfendijaM/easybosnian-daily-uploads
gh variable delete TIKTOK_EXPORT_ENABLED --repo TifahEfendijaM/easybosnian-daily-uploads
cd cloudflare
easybosnian_wrangler secret delete HC_WATCHDOG_URL --config wrangler.toml
easybosnian_wrangler secret delete NOTIFY_GITHUB_TOKEN --config wrangler.toml
```

Revoke the old notification-only GitHub PAT in its provider settings separately. Deleting a secret does not revoke a PAT. Remove/revoke the three old Healthchecks checks/ping URLs in that account when convenient. PREPARATION_RECOVERY_AUTHORIZED was not present; remove it only if later found. Do not remove GITHUB_DISPATCH_TOKEN, ADMIN_TOKEN, GH_SECRETS_TOKEN, CODEX_AUTH_JSON or any social credential.

## Explicit behaviour choices

The user chose saved/reused previews, fresh replacement on every daily invocation, complete overwrite of same-date novelty metadata, ambiguous-response duplicate risk and silence on missing runs. Immediate actual-provider verification remains; there is no durable duplicate gate. The unused manual TikTok vertical export and native-reshare switch are removed as obsolete routes; active Buffer feed/image Stories remain. No other behaviour expansion is intended.
