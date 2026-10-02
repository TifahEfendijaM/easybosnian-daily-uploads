# Setup status — 2026-10-02

The exact new private repository is `TifahEfendijaM/easybosnian-daily-uploads`. Source is uploaded and the first GitHub code/renderer check passed. Code checks do not indicate publication.

Cloudflare Workers **Free** was verified in the account's Workers plans dashboard: Free was marked **Current plan**. This project's new Worker, D1 database and KV namespace are deployed under `easybosnian-daily-tifah-v1`. The deployed health endpoint and authenticated private history were checked; history is fresh and empty. The Worker URL and generated administrative credential are stored in this repository's secrets and a protected local file. No FLUX generation or Instagram publication has been invoked during setup.

The local tool-enabled preparation automation is configured for **17:00 daily**. The GitHub pipeline schedule is **17:10 daily, Europe/Sarajevo**. There is no scheduled retry. Posting remains disabled pending working Instagram authorization, failure notifications and the first real reviewed package save/read-back. The local preparation task requires the computer awake and Codex running.

Meta currently redirects this developer account to **Account confirmation needed**, stating that confirmation is needed to regain developer access. The user must complete **Confirm Account** before a fresh Instagram app can be created. Instagram credentials, the restricted GitHub secrets-writer credential and monitoring credentials have not been configured. Do not mark this project fully operational or claim a confirmed publication.

After Meta access is restored, follow `authorization.md` to create **EasyBosnian Daily Uploads**, choose **Instagram Login**, authorize the professional `@easy_bosnian` account and enter its freshly generated token privately. Configure the free notifications described in `failures.md`, verify actual queue save/read-back, and enable the daily run under the user's existing authorization. No unpublished-preview or separate live-test approval is required.
