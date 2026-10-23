# Failures and deliberate limits

notify.failure writes build/failure.txt and opens a private issue in TifahEfendijaM/easybosnian-daily-uploads. It includes the Sarajevo date, failed stage, sanitized error, actual publication status, actionable next step and actual GitHub run link, or explicitly says no run exists. Private artifacts retain safe cards/results/diagnostics for seven days. Credentials, raw model output and private answer keys are excluded.

The October 23 05:00 run [39892704949](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/39892704949) exited during cloud research/review, before FLUX, cleanup, history saving or publication. The former wrapper reduced every nonzero Codex exit to a generic sign-in/usage message and did not preserve its underlying CLI error in artifacts. That historical message cannot establish exhausted usage, broken sign-in or a provider outage. Safe CLI reason/status artifacts now distinguish these causes when reported, without uploading raw traces or adding retries. A deliberate verify run checks current access without preparing content, generating photos or publishing.

The single workflow always writes its safe summary and attempts credential persistence after successful credential restoration. Preparation, content review or fit failure prevents publication. Private artwork renders before credential persistence; persistence failure prevents public exposure, cleanup and publication. An individual social publisher failure still allows the other independently enabled feed publishers to run. Instagram and Facebook Stories each follow their own confirmed feed publication within the current run. Failure in Instagram, including its Stories, does not suppress Facebook Stories after Facebook succeeds. Facebook Story failures keep partial returned IDs/statuses in a private result artifact and a private failure issue, without retrying. Returned known IDs are retained for a later deliberate batch-specific cleanup.

No publication state machine, reconciliation or publication retry is introduced. Known returned IDs are retained in publication_ids for the user's deliberate batch-specific cleanup. An ambiguous response without a returned ID still cannot be automatically located; inspect the account manually. A complete authenticated owned-media listing distinguishes manually deleted/expired media from a permission/network failure, which stops cleanup while independently checked replacement publishing continues. An ambiguous response may have posted successfully. Inspect the platform and the artifact before manually starting daily again; another invocation prepares replacement content and may create another post. No automatic publishing retry is sent. Read-only provider/container polling inside the current run remains.

There is no watchdog, Healthchecks, deduplicated alert table, monitor endpoint or missing-run check. If Cloudflare/GitHub never starts the run, no notification is sent. This is the user's accepted tradeoff. Cloudflare status-only dispatch logs and the private per-date cron claim remain available for manual inspection. HTTP 204 means dispatch accepted, not content or publication completed.

Turn DAILY_POSTING_ENABLED false to disable live publishing. verify and preview continue to work. If the issue API fails, the failure file and failed workflow remain available. Successful-run reports appear directly on the private GitHub run Summary page and in its artifact. Report failures are ancillary warnings and never undo or retry publication. No email sending, sending credential or paid fallback is used. See success-reports.md.

Same-date TikTok reruns have no deletion acknowledgement gate and cannot check or delete earlier posts; remove earlier versions manually if desired. Other enabled platforms continue independently. A missing or expired Instagram deletion credential produces a cleanup warning and leaves old content; publishing still performs its separate account/kill-switch checks.

The October 3 same_words replacement confirmed all three feed posts and all Instagram image Stories. Facebook returned a photo Story with status `published` while the read-back expected `PUBLISHED`. This status-case mismatch is corrected without resubmitting the accepted Story. The regression covers both cases and rejects archived media. A failed overall run may therefore contain verified feed publications and one accepted Story; inspect platform artifacts before deliberate replacement.

Facebook replacement attempts feed-post cleanup only; Story nodes and their backing photos are never deleted by this pipeline. Existing uploaded photo IDs are preserved because they mix Story/feed assets. Failed Instagram/Facebook cleanup is a warning rather than a publication gate: record it privately with the new publication outcome, retain uncertain IDs and continue through the publisher’s independent account and kill-switch checks. No retry is added. Remove old Facebook Stories/photos and TikTok posts manually if desired. Facebook Story publication checks still accept published/PUBLISHED equivalently.

Replacement cleanup selects only the latest recorded batch within the selected batch_id: the last Instagram feed post and up to three Stories recorded after it, and the last Facebook feed post. It leaves other independent batches alone and never fills a partial latest Story batch with older Story IDs. D1 insertion order is exposed as recorded_order in the authenticated ID listing; provider ID sorting is not used as a clock. If order is unavailable, cleanup warns/skips and publishing remains independently gated. Facebook Stories/photos and TikTok posts stay manual. No content history, reservation, intent, retry or daily-claim state is added.

## All-today cleanup

The explicit all_today option targets only the current Sarajevo date frozen at preparation. It renders before erasing earlier content history/private artwork and attempting all supported known IDs. History-removal or batch-cleanup errors retain uncertain IDs, warn in the summary/report and private issue, and do not block new posting. Facebook Stories/photos and TikTok remain manual. An empty current day never targets yesterday. Disabled publishing prevents destructive operations; disabled platforms are not cleaned. No automatic retry is added.

Invalid custom entered/kept words no longer force an exact misspelling into the draft: preparation first researches a correction, then chooses a suitable alternative if the intended word cannot pass its checks. Only invalid slots change, inside the same child execution; all normal final checks still apply. No scheduled, model-execution or publishing retry is added.

## Image storage visibility

Run [37182795279](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/37182795279) completed preparation, including correcting the entered lesson seed to cjenkanje. It then returned HTTP 409 at storage after rendering its first quiz card. The private JPEG was subsequently readable and matched the artifact exactly; cleanup and publishing had not begun. The old exposure route immediately reread that just-uploaded private key, which can be absent during KV propagation. These observations are consistent with that race, but the old response masked its reason and historical Workers Logs returned 403, so its exact internal error cannot be recovered.

New exposure requests send the reviewed renderer's JPEG directly to the authenticated Worker. It checks the batch, allowed final-image name, image/jpeg body, JPEG signature and 3 MB size limit, then writes one random public object with the existing 14-day expiry. It does not depend on a private KV read. Empty-body legacy exposure remains compatible and reports asset_not_visible if its private key is unavailable.

Before passing any fresh URL to Instagram, Facebook or Buffer, read it without admin credentials and compare its bytes with the renderer output. Poll only explicit HTTP 404 responses, every five seconds for up to 180 seconds with at most ten seconds per request. A byte mismatch or auth/quota/service/uncertain network error fails immediately. No upload, exposure, model execution, workflow dispatch or social publication is resubmitted. This availability wait runs within the current workflow; no scheduled retry is added. Preview remains private.

Worker storage errors now return/log only fixed reason codes and status: asset_invalid, asset_write_failed, asset_not_visible, asset_read_failed or asset_exposure_failed. Python keeps the numeric HTTP status and maps only those known codes to safe descriptions. It never logs provider exception prose, credentials or request bodies. If visibility never arrives, inspect Cloudflare's storage status/limits and the private failure artifact before deliberately starting another daily run. Existing history remains saved; all_today does not erase earlier content or attempt cleanup until every feed card has rendered and become readable.

## Confirming Instagram cleanup

Instagram cleanup checks the complete authenticated media listing once after each accepted DELETE. A surviving ID or failed read produces a cleanup warning and keeps that ID; it never repeats the DELETE, and replacement publishing continues independently. Only confirmed absence is counted as removed and forgotten. This is a read within the current attempt, without publication state, retries or a new schedule.

## FLUX inference diagnostics

The October 5 morning run [37257601710](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/37257601710) and private preview [37247992834](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/37247992834) failed at FLUX generation before publication. Cloudflare's original events record `ai_call_failed`, without a provider code. Their raw provider responses were not retained, so the exact upstream cause cannot be recovered. The dashboard showed only 518.4 of 10,000 free daily units used on October 5. A diagnostic REST request and the failed morning quiz's exact prompt through the Worker both succeeded later. These observations rule out an exhausted daily allocation at that check and confirm current model/request availability, but do not establish a historical capacity incident or timeout.

The old Python HTTP client discarded the Worker's top-level FLUX reason/code and described every HTTP 409 as a generic permissions/status problem. It now keeps only allowlisted fixed reasons, documented numeric Workers AI codes and the numeric upstream HTTP status. The artwork wrapper preserves those details through the failure artifact/private issue. Provider prose, bodies, prompts, identifiers and credentials are never logged. Other providers retain their existing nested code/subcode handling.

The Worker requests a per-inference raw Response from the same AI binding, parses the same JSON image output, and captures its status/code before the binding can reduce a failure to an exception. It does not use shared mutable `lastRequest` diagnostics. There is exactly one inference attempt, using Free FLUX.1 Schnell with four steps; the private cache and 14-day expiry are unchanged. Unknown codes are omitted rather than guessing from provider prose. Malformed/missing images fail without caching, rendering or posting.

Known codes produce specific next steps: 3036 means daily free allocation exhausted (reset at 00:00 UTC), 3040 means temporarily unavailable inference capacity, and 3007/3008 mean timeout/abort. Model/access/configuration failures and private cache errors have separate guidance. See [Cloudflare's error reference](https://developers.cloudflare.com/workers-ai/platform/errors/) and [Free allocation/reset](https://developers.cloudflare.com/workers-ai/platform/pricing/). No automatic retry, catch-up, paid fallback or extra visual-model call is added. Better diagnostics do not guarantee that Cloudflare will always have capacity; inspect the precise failure before deliberately starting another run.

## Instagram Story publishing quota

The October 20 runs [39458317828](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/39458317828) and [39485211516](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/39485211516) failed only at Instagram Story publication with HTTP 400, code 9, subcode 2207042. The earlier run confirmed its quiz Story before the second was refused; the later run was refused on the first. All three feed platforms and all three Facebook Stories were confirmed in both runs. The containers still reported FINISHED: that status describes media processing, not the account's publishing allowance.

[Meta's error reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/error-codes) identifies that exact numeric pair as publishing-limit exhaustion. It is distinct from 9007/2207027 readiness, authorization errors and spam restrictions. The HTTP wrapper now gives it a fixed quota-specific description and safe reason, without retaining provider prose or credentials. Failure issues, Story artifacts and the run's platform summary explain quota exhaustion and preserve any already-returned Story IDs.

Before rendering/uploading Stories, query the already-verified Instagram Login account's `content_publishing_limit?fields=quota_usage,config` once. Validate numeric usage, configured total and duration, never hardcode a 25/50/100-post limit. A known allowance with fewer than three free slots stops that Story set before any write. An unsupported, malformed or unavailable read is explicitly unknown: warn and preserve the existing one-attempt publishing path, without inventing zero usage or spare capacity. A snapshot is not a reservation or a guarantee; if Meta subsequently refuses a publish, record that specific refusal and stop, without a second attempt.

The quota reference describes a rolling window, not a midnight reset. Report the returned window and counts when available; do not invent an exact recovery time. Another manual workflow does not reset Meta's allowance. No delayed upload, catch-up, retry or alternate-credential fallback is added. Instagram Login still owns Stories/refresh and Facebook Login owns feed/polls. Feed publications, independent Facebook Stories, published-only history and batch-specific cleanup keep their existing behavior. `verify` now reads both authorized clients' numeric publishing quotas; the older detailed recorded-Facebook-object diagnostic remains available through `scripts/diagnose_publications.py` without the quota-only flag. Neither diagnostic publishes or deletes anything.

Read-only verification [39491163615](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/39491163615) subsequently returned usage 51, total 100 and a 86,400-second window through both existing login paths. The old failed runs did not record quota snapshots, so their exact counters cannot be reconstructed from the later reading. This does not prove a separate Story limit or a Meta bug, nor guarantee that a Story would now be accepted. A future refusal after a preflight that reported enough room is explicitly marked `quota_counter_conflict` and described in the platform summary as a publishing-limit refusal despite reported spare quota. Keep both the snapshot and actual provider code; never claim measured exhaustion when that snapshot shows room, hardcode a lower undocumented cap, or retry through a different credential to test it.

## October 21 Instagram cleanup / Story diagnosis

The 05:00 Sarajevo run 39536214152 published its Instagram/Facebook/TikTok feeds,
native poll and all Facebook Stories. Instagram confirmed two Stories before
refusing the third with 9/2207042, despite a preflight reporting 49/100 used.
The 05:26 manual latest replacement 39538544957 confirmed its Instagram/Facebook
feeds, native poll and all Facebook Stories, but its first Instagram Story was
refused with the same code after a 51/100 snapshot. These are explicit provider
publishing-limit refusals despite reported spare quota, not readiness errors.

The manual replacement's Instagram cleanup separately returned HTTP 400,
code 9/subcode 2207074. Exact account and required deletion permissions passed
a subsequent read-only check. The official media reference supports the existing
Facebook Login DELETE operation but does not establish this subcode's exact
restriction/window. Do not claim an exhausted measured deletion counter, a
specific reset, or use the publishing counter as deletion capacity. Cleanup's
existing stop-on-error behavior can leave the feed untouched when a Story fails
first. New publication intentionally remains independent.

A subsequent audit of the October 20 artifacts found exactly 50 confirmed
Instagram removals before the first 2207074 refusal: twelve cleanups removed four
items each, then run 39485211516 removed two; the next cleanup (39493733221) was
refused. No earlier workflow fell within the preceding evening. This strongly
supports a separate deletion-action limit. It is observed evidence, not a
documented quota contract: do not hardcode 50, invent a reset window, use another
token to bypass it, or retry deletion to test the theory.

Cleanup failures now retain the fixed failed operation/kind and confirmed partial
removal counts in artifacts and Summary; all_today totals include confirmed work
before a failure. No extra API call, deletion retry, catch-up, token switch or
publication is added. The same manual run also had a TikTok API-volume rejection,
confirmed in Buffer's error view (advises waiting 24 hours). No retry was clicked.
