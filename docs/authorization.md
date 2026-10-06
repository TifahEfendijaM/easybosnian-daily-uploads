# Existing authorizations and credential boundaries

Operate only on private TifahEfendijaM/easybosnian-daily-uploads and its existing isolated Free Cloudflare resources. Credentials are entered through provider authorization or hidden prompts and stored privately; never paste them into chat, source or command arguments.

## Credentials still used

| Location | Names and purpose |
|---|---|
| GitHub secrets | EASYBOSNIAN_WORKER_URL and EASYBOSNIAN_ADMIN_TOKEN: private history/images |
| GitHub secrets | CODEX_AUTH_JSON: dedicated cloud-only managed ChatGPT sign-in |
| GitHub secrets | GH_SECRETS_TOKEN: refresh/persist cloud and Instagram credentials, restricted to this repository |
| GitHub secrets | INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID, INSTAGRAM_TOKEN_ISSUED_AT, META_GRAPH_VERSION: exact professional @easy_bosnian account and supported Graph version |
| GitHub secrets | INSTAGRAM_DELETE_ACCESS_TOKEN, INSTAGRAM_DELETE_USER_ID: separate Facebook Login authorization for same-date Instagram deletion only |
| GitHub secrets | FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN: independently authorized Easy Bosnian Page 1284422991426579 |
| GitHub secrets | BUFFER_API_KEY: Free Buffer account:read/posts:read/posts:write key |
| Worker secrets | ADMIN_TOKEN: authenticates private history/image operations |
| Worker secrets | GITHUB_DISPATCH_TOKEN: only this repository, Actions read/write + Metadata read; starts workflows |

GITHUB_DISPATCH_TOKEN expires 2027-10-03. BUFFER_API_KEY expires 2027-10-03. The existing GH_SECRETS_TOKEN expires 2026-12-31. Renew before expiry, without sharing a token or expanding to other repositories. Instagram's unexpired long-lived token refresh at day 40 and immediate private persistence remain unchanged. Facebook authorization remains separate from Instagram Login. The Meta app's public distribution authorization is already completed.

The pipeline checks the exact Instagram username/professional type, Facebook Page name/ID and Buffer @easy.bosnian channel/organization/service identity, connected/unpaused state, publishing scopes and automatic (non-reminder) setting. Buffer sends the three reviewed images and caption, checks actual rehosted bytes in order and requires sent status plus a TikTok permalink. This is Buffer confirmation, not an independent TikTok API read-back. No direct TikTok app, music picker, private-profile change or paid Buffer plan is introduced.

Automatic Instagram and Facebook image Stories upload exact reviewed text with treatment B for every card (quiz question above the complete photo, choices below). Facebook Stories use the existing separate Page token and pages_manage_posts, pages_read_engagement and pages_show_list permissions; no broader consent or additional credential is introduced. Fresh unpublished photos are uploaded separately from feed media, then photo_stories publishes them. Protected connection checks read /PAGE_ID/stories without publishing. FACEBOOK_STORIES_ENABLED controls Facebook Stories alongside FACEBOOK_POSTING_ENABLED and the global live kill switch. Highlights (Pitanje dana, Znaš li?, Riječ dana) and TikTok Stories remain manual. INSTAGRAM_STORIES_ENABLED controls Instagram image Stories; the obsolete native-reshare mode switch is unused.

Current API references: [Meta Page Stories](https://developers.facebook.com/documentation/video-api/page-stories-api), [TikTok photo publishing](https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post) and [Buffer API](https://developers.buffer.com/reference.html). TikTok/Buffer expose feed publishing, not an automatic Story option. Buffer deletion cannot remove already-published TikTok content.

## Unused after this branch is deployed

- GitHub secrets: **HC_PIPELINE_URL**, **HC_PREPARATION_URL**.
- Worker secrets: **HC_WATCHDOG_URL**, **NOTIFY_GITHUB_TOKEN**. The latter's notification-only PAT can be revoked; it is separate from GITHUB_DISPATCH_TOKEN.
- Existing repository variables: **CLOUD_PREPARATION_ENABLED**, **INSTAGRAM_STORY_MODE**, **TIKTOK_EXPORT_ENABLED**.
- **PREPARATION_RECOVERY_AUTHORIZED** is removed from the design; it was not present in the repository-variable listing during this review.
- EXPECTED_PACKAGE_HASH and BATCH_DATE workflow environment/output plumbing are removed; they are not stored secrets in the current listing.
- D1 settings flags daily_enabled, daily_authorized, preparation_verified, active_since, healthchecks_deferred, monitoring_ready and github_monitoring_ready disappear with the settings table. They are not GitHub variables to revoke.

DAILY_POSTING_ENABLED, FACEBOOK_POSTING_ENABLED, TIKTOK_POSTING_ENABLED, INSTAGRAM_STORIES_ENABLED, FACEBOOK_STORIES_ENABLED, BUFFER_TIKTOK_CHANNEL_ID and BUFFER_ORGANIZATION_ID remain. PREPARATION_DISPATCH_ENABLED remains a Worker configuration variable. GitHub issues use the workflow's native GITHUB_TOKEN; the Worker no longer needs an issue token.

Remove obsolete secrets/variables and revoke the old notification PAT only after rollout. See migration-and-rollout.md for the exact sequence and commands. No live credential is removed during branch review.

Instagram deletion uses [Meta Instagram Media deletion](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media), which currently supports Facebook Login only and requires instagram_basic + instagram_manage_contents. It needs the exact Page/profile link and a separate long-lived Facebook User token; publishing tokens remain unchanged. Renew this finite-lived deletion credential through explicit Facebook Login before its documented expiry. [Facebook Page post deletion](https://developers.facebook.com/documentation/pages-api/posts) uses the existing Page token. See manual-reruns.md for scope and safeguards.

Cleanup is independent of publishing. Instagram deletion credential failure leaves old content and records a warning; it no longer blocks a replacement upload. Facebook uses supported feed-post deletion only; its Story nodes and backing photos are never deleted by this pipeline. No added permission or credential is requested for a speculative Story deletion workaround.

## Retaining Facebook access during Instagram consent

Meta consent for this shared app must retain every previously authorized Page/Instagram permission. The October 6 failures were HTTP 403/code 200 at the first photo upload after pages_manage_posts disappeared from the current consent. The exact Page credential was renewed privately with all three Page scopes and verified as a valid Page token with can_post=true. Page connection checks now require that capability before any upload. Provider status/code and failed stage are kept in the platform result and run summary; authorization failure never starts another publish attempt.
