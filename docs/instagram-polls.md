# Native Pitanje dana caption polls

The Instagram feed publisher uses Instagram API **with Facebook Login** on
`graph.facebook.com`. Meta introduced caption add-ons on September 28, 2026.
The original Instagram Login token remains responsible for unchanged image
Stories and its existing long-lived refresh/persistence. Facebook Page posts,
Buffer TikTok, scheduling, batch replacement and deletion safeguards are unchanged.

## Authorization and rollout

The read-only cloud authorization audit on October 6 confirmed the existing
deletion token authorizes the exact linked Page/profile but lacks
`instagram_content_publish`. Do not reuse it as a publishing token or use the
Facebook Page token: the poll read edge requires a **Facebook User token**.

Authorize the existing EasyBosnian Daily Uploads app (1987873818544936) for only
Easy Bosnian Page 1284422991426579 and its linked professional @easy_bosnian:
`instagram_basic`, `instagram_content_publish`, `pages_read_engagement` and
`pages_show_list`, plus `ads_read` for this Business-Manager-assigned Page.
Business Suite confirms the user already has full access to the exact Page;
`business_management` is additionally requested for business-owned asset
discovery/task verification. Retain the previously authorized
`pages_manage_posts` and `instagram_manage_contents` when renewing consent;
dropping them breaks the independent Facebook/deletion credentials. Verify
MANAGE or CREATE_CONTENT on the exact Page from the authenticated accounts edge.
No assignment is changed and no broader permission is silently substituted.
Both additional scopes were explicitly approved and consented to on October 6.
The renewed token passed the exact Page/profile and MANAGE/CREATE_CONTENT task
checks, and its separate repository secrets were saved before merge. Protected
credentials are not included in `instagram-poll-authorization.json`; that file
records only the verified identity, required scopes and effective expiry.

Use `easybosnian authorize-instagram-polls` with its hidden prompts, never token
arguments. It exchanges once, checks app ID, USER token type, scopes, expiry,
exact Page/profile and content tasks, then stores separate repository secrets:

- `INSTAGRAM_FACEBOOK_ACCESS_TOKEN`
- `INSTAGRAM_FACEBOOK_USER_ID`
- `INSTAGRAM_FACEBOOK_EXPIRES_AT` (earliest positive token/data-access expiry)

The authorization metadata contains no credential. These Facebook User tokens
have finite access: renew through explicit consent before expiry. Never refresh
them with the Instagram Login refresh endpoint. Existing Stories/deletion/Page
credentials are not replaced. New secrets remain outside the research child's
stripped environment. Save and verify authorization **before merging** the
workflow that requires it, so the next scheduled run remains operational.

Review the complete branch diff and tests, configure/verify the separate token,
then merge repository changes. No Worker deploy, cron change, migration or live
test publication is needed. A branch `verify` run is read-only: no content,
container, poll, Story or deletion is created. A successful connection check is
not proof of a live poll; the next normal publication performs attachment/read-back.

## Exact payload and limits

`poll_attachment` is serialized compact JSON containing only `option_a`,
`option_b` and optional consecutive `option_c`/`option_d`. It uses Pitanje dana's
reviewed **2–4 choices in original order**, without letters prepended, a correct
flag, answer key, aliases, rationale or review metadata. It is sent only when
creating the **parent CAROUSEL container**, never on a child slide.

Each option is 1–25 visible characters; Unicode grapheme measurement preserves
Bosnian accents and counts compound emoji as single characters. The actual
serialized JSON must be at most 200 Unicode code points, counted conservatively
because Meta does not document emoji counting for serialized JSON. Escapes,
keys and punctuation count. Answers with outer whitespace are omitted from the
native poll because Meta trims it. Source choices are never normalized,
shortened, replaced or reordered.

**User-approved limit policy:** if an otherwise reviewed choice/payload exceeds
these limits, publish the unchanged carousel without the native poll and make
the omission visible in the run Summary/result/success report. This is not a
retry or a rewritten quiz. Invalid quiz structure is still a content failure.

The Instagram caption includes the exact Bosnian quiz question and preserves
the reviewed difficulty prose and website invitation, ending with
`👉easybosnian.com`. Existing hashtags appear before the final invitation.
Legacy captions without this footer remain readable. The combined caption must
fit 2200 characters, 30 hashtags and 20 mentions; overflow fails without silent
truncation. Other platforms' captions are unchanged.

## Publish/read-back and partial failure

There is exactly one `media_publish` request. Record the known feed ID immediately
for batch-scoped cleanup. Inspect `caption_add_on_attachment_status`: omission
means attachment success according to Meta; `POLL_CREATION_FAILURE` means the
post can already be published without its poll. Unknown/contradictory outcomes
are treated as unconfirmed, with status-only diagnostics.

Read `GET /MEDIA_ID/poll_attachment` as a separate call, not field expansion.
Confirm every option against the original ordered payload, including absence of
unused options. Vote totals/shares are not a correctness signal and are not
logged. Missing, mismatched or unreadable polls, reported creation failure, and
contradictory responses produce a clear private failure issue and run result.
Confirmed feed publication still allows unchanged Stories and independently
enabled Facebook/TikTok. The overall run reports poll failure after those
attempts; it never republishes or retries. A timed-out publish remains ambiguous
under the existing no-retry rule. Meta does not support repairing a poll after
publication. Existing content validation and answer secrecy remain intact.

Stories have **no native poll**; Meta caption add-ons do not support them.

Official references: [Caption add-ons](https://developers.facebook.com/documentation/instagram-platform/content-publishing/caption-add-ons),
[IG User Media](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media),
[Poll Attachment](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-media/poll_attachment).
