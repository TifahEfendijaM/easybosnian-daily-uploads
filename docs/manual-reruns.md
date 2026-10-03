# Deliberate same-day replacement

Open GitHub Actions → EasyBosnian daily preparation and publishing → Run workflow. Select **daily**, then:

| content_selection | Result |
|---|---|
| new (default) | New theme and three new words, compared with all current history |
| same_theme | Keep today's exact theme metadata; choose three different words |
| same_words | Keep today's theme and three words in the same order; research fresh questions, explanations, examples and background prompts |

Reuse requires today's complete content row. Old metadata-only imports cannot be rendered or used as a reuse source. All choices re-review sources, Bosnian correctness, quiz secrecy, schema and measured fit. Only explicitly reused same-date metadata is exempt from novelty checks; older rows remain authoritative. Every newly prepared batch must use three distinct layouts. Preview still reuses today's row without publishing or deleting. Verify only checks connections/workspace. The scheduled Worker sends mode=daily and receives the default new selection; no dispatch API or cron-claim changes are needed.

Preparation saves today's replacement row and invalidates cached artwork. After fresh cards render successfully, cleanup checks only that date's stored provider IDs on the verified publishing account. It lists owned media completely before treating a missing ID as manually deleted/expired. Permission, pagination or network errors stop that platform; they never count as already deleted. Known old Instagram carousels and image Stories, Facebook feed posts, photo Stories and uploaded photos are removed before that platform posts replacement content. The global publishing switch also gates deletion. Disabled platforms are not cleaned. Other enabled platforms continue independently after a failure.

There is a small private publication_ids table with date/platform/kind/object_id/account_id only. IDs are written immediately after a provider returns them, before read-back, including partial results. Deleted/confirmed absent IDs are removed. It is not a publication state machine: no intents, hashes, revisions, immutable packages, retries or completion gate. A request that times out without returning an ID may still have published and cannot be located automatically. Likewise, an accepted Buffer submission remains a known ID even while upstream publication is pending. Inspect uncertain outcomes manually.

**TikTok:** Buffer cannot delete an already-published TikTok post. Delete today's old post in TikTok yourself, then tick **tiktok_previous_removed** for the rerun. Without acknowledgement, TikTok replacement fails explicitly; Instagram and Facebook can still proceed. A first upload needs no acknowledgement. This acknowledgement does not call Buffer deletePost or claim API deletion.

**Facebook:** Existing Page token permissions pages_manage_posts, pages_read_engagement and pages_show_list are retained. No new Facebook publishing/deletion consent or token is introduced. Meta's Page post/photo deletion endpoints return success; no deletion POST is retried.

**Instagram:** Deletion uses the distinct Instagram API with Facebook Login, instagram_basic and instagram_manage_contents, through Page 1284422991426579 and verified @easy_bosnian. It requires that Page and professional Instagram profile to be formally linked. Save **INSTAGRAM_DELETE_ACCESS_TOKEN** (long-lived Facebook User token) and **INSTAGRAM_DELETE_USER_ID** (Facebook Login's Instagram ID) privately. The existing Instagram Login publishing/refresh credentials remain untouched. Authorize with `easybosnian authorize-instagram-deletion` using hidden prompts. Meta's Facebook User token has a finite lifetime; reauthorize before the expiry in docs/instagram-deletion-authorization.json when deletion is needed. There is no unattended Facebook User-token refresh added. An expired/missing deletion token affects same-date Instagram replacement, not a first new-date publication.

# Layout selection

The catalog is the renderer's geometry source: x/width/anchor, label alignment, heading alignment and approved heading size. FLUX does not receive these numbers. Preparation picks layouts first and uses at most one natural framing phrase from the actual scene_focus direction, preserving a relevant photorealistic subject in the visible portion. Narrow columns require concise copy; measured fit can reject them. Dynamic body fonts remain 44/38/34 px at 160/240 character boundaries, with measured line heights, contrast and unchanged Bosnian diacritics. Separate PRIMJER label and inset accent remain.

# Deployment sequence

1. Review the full branch diff and all eight layout previews. Run Python and Worker tests, including dense-card fit, selection exemptions, kill switch, partial IDs and ownership/pagination failures.
2. Merge repository changes into main. The workflow retains exactly verify/preview/daily and accepts optional content_selection and tiktok_previous_removed; the Worker payload remains mode=daily, so no 422 transition is introduced.
3. Apply D1 migration 0004_publication_ids.sql to this existing database only. It adds an empty identifier table/index, carries history and cron claims unchanged and drops no data.
4. Validate the real ignored wrangler.toml and example against the Worker gate, deploy this same Worker, then read its actual version, registered `0 3,4 * * *` cron and protected publication-ID endpoint back. The start remains 05:00 Sarajevo, selected from scheduledTime for DST; there is no retry/catch-up.
5. Complete the separate Instagram deletion authorization and save its exact two repository secrets. Run read-only identity/permissions checks; no live deletion/publication test is necessary or authorized by rollout.
6. For today's pre-feature successful run, optionally import its known IDs with `python scripts/import_publication_ids.py --run 37119858010 --date 2026-10-03`. The importer checks exact private repo, main workflow/date/success and unique daily artifact, reads only safe diagnostic IDs, then saves/read-verifies them. It does not restore rejected content, touch novelty history or delete any social content. Old runs without available diagnostic IDs are not guessed from account posts.
7. Confirm the ordinary main checks pass. Leave the next run to the 05:00 external clock; do not dispatch a manual daily test or retry.
