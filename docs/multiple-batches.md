# Multiple independent batches

## Semantics

The form exposes batch_target=latest/none/all_today. latest replaces exactly the newest complete saved batch by created_at and created_order (D1 insertion order), keeping its batch_id/date and creation order. none adds a new UUID batch for the current Sarajevo date, without deleting or overwriting any earlier content, artwork or publication IDs. The latest source may supply same_words/same_theme/custom defaults for all targets (all_today prefers a complete current-date source). The four selection rules and fresh text/design generation stay intact. Explicit retained terms may repeat across independent copies; new terms compare against every batch. latest overwrites only its selected content, removing that version’s old novelty terms; none keeps them.

After midnight, latest can replace yesterday’s batch; none is an additional batch for today. The automatic 05:00 dispatch sends daily/none, with default selection new. It adds the morning’s batch even if a manual addition was saved earlier that date. A preview is saved content and may be the latest source; neither preview nor verify deletes/posts. Failed or unpublished saved content also remains a possible latest source: there is no publication-state gate.

## Migration 0005

history’s date primary key becomes batch_id. Keep date as a nonunique indexed content date. Add created_at, assigned once by the Worker; expose rowid as created_order for timestamp ties. Existing rows receive deterministic legacy-YYYY-MM-DD IDs. Their initial timestamps use available private_review.reviewed_at, converted to UTC, or midnight UTC of the content date. These are estimates because the old table never stored actual creation time. Metadata-only historical imports retain their original content/aliases and do not become renderable batches.

Every publication_ids row keeps its provider/account/date/kind and original rowid, and gains legacy-YYYY-MM-DD. Orphan IDs without a content row are retained. Historical same-date content versions already overwritten before this migration cannot be recovered; no old Git artifact or rejected package is restored. Legacy ID buckets may contain several historical publication sets, so cleanup still selects only their last feed and following up-to-three Stories, never all old items. New batches’ IDs are independent from the outset.

No live content, known ID or cron claim is dropped. The obsolete physical table layouts are replaced, not their data. Public URLs and their 14-day expiry stay intact. Migrated private image caches remain readable through a legacy fallback until replacement/expiry; replacement invalidates only its own ID namespace and, for that exact legacy row, its former date namespace. Another batch on the same date never uses or invalidates that fallback. No publication state, hash, revision, reservation, queue, reconciliation, watchdog or retry is added.

## Backward compatibility

GET /v1/history retains its days list, now with one entry per batch, including duplicate dates, plus batch_id/created_at/created_order and storage_version=2. New protected paths are /v1/history/batches/{batch_id}, /v1/publications/batches/{batch_id}, /v1/private/batches/{batch_id}/{name} and /v1/expose/batches/{batch_id}/{name}; generation binds the reviewed prompt to batch_id and date. Existing unambiguous date routes still work; history date reads return that date’s newest row, while ambiguous date writes, publication-ID operations and image generation/storage return 409. They never guess a destructive target. Use explicit IDs for new integrations/imports. The one-time publication-ID importer reads batch_id from current artifacts, or requires --batch-id for ambiguous legacy artifacts; it rejects cross-batch IDs and supports after-midnight replacement dates. The deprecated Python today alias creates a new independent current-date batch but is absent from the form and Worker dispatch.

The publisher reads the trusted preparation-result batch ID/date. Stored content is checked for schema/editorial flags/quiz secrecy; full-history novelty, with explicit reuse, is checked during trusted preparation/save. Artifact directories and safe results include batch_id so same-date runs do not collide. No model/provider credential enters these identifiers or logs.

## Exact safe rollout

1. Review the task branch’s full diff and existing card fixtures; require all Python/Worker tests and PR checks.
2. Read only this repository’s active preparation runs. Wait for any active/queued content run to finish. Briefly set DAILY_POSTING_ENABLED=false through the guarded exact-repository helper so a new live attempt fails before content/publication during the storage cutover. Keep the previous value for restoration.
3. Merge repository changes to main first; verify the workflow accepts none before the Worker can send it. The clock has a margin before 05:00; no catch-up or claim reset.
4. Capture a private local backup of both live tables, including rowids, solely for this migration. Confirm existing Worker/D1/KV identity and clock. From cloudflare run the existing guarded Wrangler helper:

   `wrangler d1 migrations apply easybosnian-daily-tifah-v1 --remote --config wrangler.toml`

   It must apply only 0005; earlier migrations remain recorded and must never be replayed. Do not run a raw copy of migration 0003.
5. Deploy this same Worker with the existing ignored config using the guarded deploy helper (`wrangler deploy --config wrangler.toml`). No new resource or credential is needed. Read back storage_version=2, every migrated content/ID/count/order, the live none dispatch, project/resource bindings, enabled cron and only `0 3,4 * * *` with 05:00 Sarajevo gating. Public URLs stay unchanged.
6. Require exact-main checks, including protected read-only infrastructure/account checks. Restore the saved DAILY_POSTING_ENABLED value only after migration/deployment verification succeeds. Keep the clock and cron claim unchanged. Do not manually launch a daily/preview/live deletion test; the user will try the form.

If any deployment/migration verification fails, keep live publication paused and report the exact stage. Do not restore a discarded package, reset a claim, retry publication or fall back to a paid service.

## Replace all current-date batches

batch_target=all_today creates a new UUID batch for the frozen current Sarajevo date. Before research, the trusted wrapper freezes every earlier same-date history batch and every batch with known publication IDs for that date, including IDs whose history was previously erased. It prefers the latest complete same-date row for reuse; if today is empty, it may use the latest complete older row as a source just like none, but never targets that older row for cleanup. All history remains available for novelty/review until the replacement has been saved and successfully rendered. Daily then removes the frozen earlier same-date history rows and their private artwork, allowing their themes/words to be selected on future runs, and attempts all their known Instagram feed/Story and Facebook feed IDs. It preserves the new row, other dates, and unsupported/uncertain publication IDs; those IDs carry no content novelty and are retained only for ownership-scoped cleanup. Facebook Stories/photos and TikTok remain manual; disabled platforms are not cleaned. Cleanup/history-removal failures warn but do not block independently gated posting. Public random image URLs retain their original 14-day expiry. Empty today behaves like none with no fallback deletion of yesterday. Preview only saves/renders a new private batch and never removes history or social content; verify remains read-only. No new table, migration, retry, state machine or clock change is needed.

This compatible extension needs no migration. Deploy the Worker endpoints first, verify its unchanged daily/none dispatch and live cron, then merge the updated form. This is separate from the historical migration-0005 cutover described above; do not reapply that cutover or reset the publishing switch for this endpoint-only change.
