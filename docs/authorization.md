# Required authorizations

Only use the exact private repository **TifahEfendijaM/easybosnian-daily-uploads**. The repository's creation and deployment are authorized by the user. Preview and separate live-test gates were explicitly waived; do not require those steps again.

## GitHub

Sign GitHub CLI in as TifahEfendijaM using its browser/device flow. The setup helper checks the exact owner/repository and private visibility before every GitHub API operation. Keep Actions enabled, and set the Actions spending budget to $0 with usage blocked at the limit. Cloud preparation uses the native workflow token with Contents write and Issues write. Its separate managed ChatGPT sign-in and private refresh storage are described in [cloud preparation](cloud-preparation.md).

For unattended token refresh, create a fine-grained personal access token restricted to **only easybosnian-daily-uploads**, with repository **Secrets: read/write** and **Contents: read** (metadata is automatic). Store it using the hidden prompt: `easybosnian set-secret GH_SECRETS_TOKEN`. Choose a duration you can maintain, record its expiry and replace it privately before expiry. If refresh is due and this token is missing/expired, publishing stops and reports authorization failure.

For the monitoring Worker, create a separate fine-grained token restricted to the same repository, with **Actions: read** and **Issues: read/write**. Enter it privately with `easybosnian set-worker-secret NOTIFY_GITHUB_TOKEN`. The helper checks this project's deployed Worker and bindings before storing the Cloudflare secret; it never prints the value. It only reads runs and opens failure issues in the fixed target repository. No other repository is queried.

## Cloudflare

Sign in through official Wrangler OAuth; credentials are encrypted locally with a key in macOS Keychain. Use Workers **Free**. The deploy helper creates a new database, KV namespace and Worker with the unique identifier `easybosnian-daily-tifah-v1`, rather than selecting a similarly named existing project. The Worker AI binding runs `@cf/black-forest-labs/flux-1-schnell` without a broad Cloudflare deployment credential in Actions. No R2 bucket or checkout exists.

The deploy helper generates a new random `ADMIN_TOKEN`, stores the corresponding `EASYBOSNIAN_ADMIN_TOKEN` and Worker URL in this repository's Actions secrets, and keeps a protected local copy for the daily preparation task. Public history/queue endpoints do not exist. Only generated final JPEGs get temporary public random URLs for Instagram to fetch.

## Instagram — start here after infrastructure

The current official guide was read directly on 2026-10-02. The route is **Instagram API with Instagram Login**. It explicitly does not require a linked Facebook Page.

1. Ensure `@easy_bosnian` is a professional Business or Creator account in Instagram.
2. Open [Meta developer apps](https://developers.facebook.com/apps/), complete developer registration if necessary, and create a new Business-type app named **EasyBosnian Daily Uploads** with the Instagram use case. Keep its identifier separate from unrelated projects. Meta may require account/identity checks; complete those yourself.
3. Open **Instagram → API setup with Instagram business login**. If the dashboard uses “Instagram Login,” choose that route. Do not choose Instagram API with Facebook Login.
4. Add the Instagram professional account and the necessary app/tester roles for your own account. Accept any tester invitation in Instagram's app/website permissions area. The developer's Facebook account may manage the app; that does not require linking the Instagram account to the EasyBosnian Facebook Page.
5. Request only **instagram_business_basic** and **instagram_business_content_publish**. The older `business_basic` and `business_content_publish` scopes were deprecated in January 2025. For accounts with an app role, Standard Access can be used within the allowed role/account restrictions. Advanced Access for other users requires App Review and any business verification Meta requests. Account roles and dashboard availability must be checked in your actual app.
6. Click **Generate token** beside `@easy_bosnian` and log in directly to Instagram. The official guide states dashboard-generated tokens are long-lived for 60 days; tokens from the custom Business Login flow start at one hour and require server-side exchange before use. This setup deliberately uses a freshly generated dashboard token.
7. Enter that freshly generated token only into the local hidden `easybosnian authorize-instagram` prompt. The helper queries `/me?fields=user_id,username,account_type` at the supported Graph version shown by Meta (the guide currently uses v26.0), verifies the exact username and professional account type, discovers the user ID and saves the token/ID/issued time/version to repository secrets. Do not paste the token into chat or a committed file. No test post is made.
8. After the first actual reviewed preparation save/read-back, activation enables publication after successful daily preparation and the three-minute wait under the user's existing authorization. The user deferred Healthchecks until Instagram works; `healthchecks_deferred` plus independently verified `github_monitoring_ready` permits activation during that phase. Full `monitoring_ready` remains false. The first actual daily run must be reported as successful only after the returned media ID, exact caption, three carousel children and permalink have been verified.

The pipeline refreshes the unexpired long-lived token around day 40 via `graph.instagram.com/refresh_access_token` with `grant_type=ig_refresh_token`. Meta requires the token to be at least 24 hours old; expired/revoked tokens require fresh authorization. The refreshed credential is saved back to GitHub secrets immediately. Routine authorized posts do not need daily permission prompts. Revocation, loss of a role, expired data access or an expired secrets-writer token will still stop the pipeline honestly.

Official sources:

- [Instagram Login overview and current scopes](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login)
- [Get started: dashboard tokens, `/me`, professional account fields](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started)
- [Business Login token exchange and refresh](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Instagram publishing reference](https://developers.facebook.com/documentation/instagram-platform/content-publishing)

## Facebook — current setup priority

Use an independent Facebook Pages login through the personal account that manages the Page. Request **pages_show_list**, **pages_read_engagement** and **pages_manage_posts**. Obtain a supported long-lived user token, call `/me/accounts?fields=id,name,tasks,access_token`, and select the exact **Easy Bosnian** Page (1284422991426579), whose displayed name and ID were confirmed in the consent screen on 2026-10-03. Store **FACEBOOK_PAGE_ID** and **FACEBOOK_PAGE_TOKEN** separately in this repository's secrets. Verify the authorized Page ID/name before a Facebook publisher is enabled; never reuse an Instagram token here.

The existing project app **EasyBosnian Daily Uploads (1987873818544936)** supports Pages, and its Pages use case was added on 2026-10-03. Keep using this app. The separate Pages publisher is implemented and remains disabled until independent Page authorization finishes. App Review/Advanced Access and public app requirements depend on the actual roles/configuration. Long-lived Page tokens may lack a scheduled expiry but can still be revoked by role/password/security changes; do not promise permanent credentials. Instagram still never requires a Page link.

Use Graph API Explorer with this exact app and only the three permissions above. Authorize only the EasyBosnian Page. Record its confirmed Page ID. Enter the generated Facebook **user** token and this app's secret into `easybosnian authorize-facebook` using its hidden prompts. The helper exchanges the user token, finds the exact Page ID/name and publishing task, verifies the resulting long-lived **Page** token, stores only the Page token/ID in the exact repository. Credential storage alone does not arm Facebook. The app secret and user token are not saved. No test photo/post is created during authorization. The actual Meta Publish screen currently requires a privacy-policy URL. The project implements its own static `/privacy` page on its existing Free Worker. Complete the remaining app checklist and confirm its published state before enabling FACEBOOK_POSTING_ENABLED. Confirm Meta's public app requirements before claiming public distribution; a token or developer-only result does not prove public visibility.

The daily handoff attempts Instagram and Facebook independently, reusing the same cached artwork. Facebook uploads the three photos unpublished as a staging step required by Meta, then creates one three-photo Page post. This is part of the actual daily publication, not a separate unpublished test. It saves intent before each write and independently reads back the Page, exact caption, three photo IDs and permalink. Timeouts never cause blind reposts. Use `easybosnian facebook --mode reconcile --date YYYY-MM-DD` for read-only reconciliation.

[Official Pages API guide](https://developers.facebook.com/docs/pages-api/getting-started/)

## Instagram Stories and Highlights

The user requested all three published Instagram slides as Stories. The pipeline pads the exact published 1080×1350 cards to 1080×1920 without cropping, rewriting or changing their watermark. It posts only after independently verifying the daily feed carousel. Each Story has its own saved intent, container/media IDs, actual account/Story read-back and permalink. Partial or uncertain publication cannot be silently repeated. Known media IDs can be checked using `easybosnian stories --mode reconcile --date YYYY-MM-DD`.

Meta's documented IG User operations do not include creating Highlights or adding Stories to them. This part requires a manual action in Instagram: add the quiz Story to **Pitanje dana**, the lesson to **Znaš li?**, and the word to **Riječ dana**. The private daily artifact includes these mappings and verified Story links, and never claims Highlight completion. Enable native Story archiving if you want to add them after their 24-hour visibility period.

- [Publishing Stories](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [Story specifications](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media)
- [Supported account operations](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user)

## TikTok — explicitly skipped

The user cancelled all TikTok setup on 2026-10-03. TIKTOK_EXPORT_ENABLED is false and its developer login tab was closed. No TikTok app, token, sandbox, account-privacy change, API upload or post exists. The optional export command remains dormant; no daily TikTok files are created. Do not resume this route without a new user request.

For the recorded decision: Personal and Creator accounts can use an approved app. Public Direct Post needs approval/audit, and TikTok excludes internal account-management utilities. Unaudited Direct Post requires SELF_ONLY and a private account at posting time. Sandbox login/development alone does not require a private profile; this restriction concerns posting through the unaudited client. A private GitHub repository is not itself the issue. The user declined changing @easy.bosnian's public visibility.

- [Official Direct Post guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)
- [General app-review criteria](https://developers.tiktok.com/docs/en/app-review-guidelines)
- [Sandbox restrictions](https://developers.tiktok.com/docs/en/add-a-sandbox)

## Music

Facebook's photo-post API has no music picker. Instagram's current Audio API supports searching/selecting authorized tracks for Reels through Facebook Login, which requires a linked Page; it is unavailable for this project's independent Instagram Login and image carousels. No music is added by this project. TikTok's photo Direct Post API has auto_add_music for recommended music rather than a particular song; TikTok itself is skipped.

- [Instagram Audio API](https://developers.facebook.com/documentation/instagram-platform/content-publishing/audio-api)
- [TikTok photo API](https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post)
