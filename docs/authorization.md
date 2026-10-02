# Required authorizations

Only use the exact private repository **TifahEfendijaM/easybosnian-daily-uploads**. The repository's creation and deployment are authorized by the user. Preview and separate live-test gates were explicitly waived; do not require those steps again.

## GitHub

Sign GitHub CLI in as TifahEfendijaM using its browser/device flow. The setup helper checks the exact owner/repository and private visibility before every GitHub API operation. Keep Actions enabled, and set the Actions spending budget to $0 with usage blocked at the limit. The preparation automation uses this authorized local login to save queue files.

For unattended token refresh, create a fine-grained personal access token restricted to **only easybosnian-daily-uploads**, with repository **Secrets: read/write** and **Contents: read** (metadata is automatic). Store it using the hidden prompt: `easybosnian set-secret GH_SECRETS_TOKEN`. Choose a duration you can maintain, record its expiry and replace it privately before expiry. If refresh is due and this token is missing/expired, publishing stops and reports authorization failure.

For the monitoring Worker, create a separate fine-grained token restricted to the same repository, with **Actions: read** and **Issues: read/write**. Enter it privately as the Cloudflare `NOTIFY_GITHUB_TOKEN` secret. It only reads runs and opens failure issues in the fixed target repository. No other repository is queried.

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
8. Once preparation save/read-back and free monitoring are working, activation enables the 17:10 daily workflow under the user's existing authorization. The first actual daily run must be reported as successful only after the returned media ID, exact caption, three carousel children and permalink have been verified.

The pipeline refreshes the unexpired long-lived token around day 40 via `graph.instagram.com/refresh_access_token` with `grant_type=ig_refresh_token`. Meta requires the token to be at least 24 hours old; expired/revoked tokens require fresh authorization. The refreshed credential is saved back to GitHub secrets immediately. Routine authorized posts do not need daily permission prompts. Revocation, loss of a role, expired data access or an expired secrets-writer token will still stop the pipeline honestly.

Official sources:

- [Instagram Login overview and current scopes](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login)
- [Get started: dashboard tokens, `/me`, professional account fields](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started)
- [Business Login token exchange and refresh](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Instagram publishing reference](https://developers.facebook.com/documentation/instagram-platform/content-publishing)

## Facebook — after Instagram works

Use an independent Facebook Pages login through the personal account that manages the Page. Request **pages_show_list**, **pages_read_engagement** and **pages_manage_posts**. Obtain a supported long-lived user token, call `/me/accounts?fields=id,name,tasks,access_token`, and select the exact **EasyBosnian** Page by name and its confirmed Page ID. Store **FACEBOOK_PAGE_ID** and **FACEBOOK_PAGE_TOKEN** separately in this repository's secrets. Verify the authorized Page ID/name before a Facebook publisher is enabled; never reuse an Instagram token here.

Use the same Meta app only if its allowed use cases/products support the independent Pages route; otherwise create a separate Business app for Pages. App Review/Advanced Access requirements depend on the roles and app configuration. Long-lived Page tokens may lack a scheduled expiry but can still be revoked by role/password/security changes; do not promise permanent credentials. The current Instagram pipeline never calls Facebook publishing and never requires a Page link.

[Official Pages API guide](https://developers.facebook.com/docs/pages-api/getting-started/)

## TikTok — investigation only

TikTok's official Direct Post guide says unaudited clients' posts are restricted to private viewing. Its developer guidelines require a real creator-facing experience with user control and disallow clients limited to internal/private utilities. A single-brand unattended uploader may not qualify for a public-posting audit. Do not promise unattended public TikTok posting or add a paid service workaround. The renderer can export 1080×1920 files for a later approved/manual workflow; no TikTok token or posting code is enabled.

- [Direct Post getting started](https://developers.tiktok.com/docs/en/content-posting-api-get-started)
- [Official content-sharing guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines)
