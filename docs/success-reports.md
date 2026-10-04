# Successful-run reports

After successful daily publication, including manual reruns, the single job creates a private report for the exact prepared batch ID. It contains content date, theme, shared difficulty, palette, per-card layout, the three exact FLUX prompts and confirmed feed/Story links/statuses. It does not include credentials, private answer keys, source-review notes or raw model output. A small local, whitelisted report-source.json captures the exact rendering input before generation; reporting never rereads a history row that a later replacement could have overwritten. This is a run artifact, not an immutable package or publication state machine. Markdown/HTML/JSON reports are stored only in the private GitHub artifact (seven days) and the run summary. No public Worker route or new database table is added. Links reflect confirmation at the time of the run, not permanent availability after replacement or Story expiry.

Verify and preview do not create publication-success reports or send email. A failed or partial publication creates no success report. Existing failure artifacts/issues remain. Cleanup warnings may accompany a successful replacement; the report notes that old content may remain.

Optional email is sent once, at the end of the successful job after artifact upload, through Gmail’s TLS SMTP endpoint smtp.gmail.com:465. The sender and sole recipient are REPORT_EMAIL_TO, the user-authorized Gmail address. The REPORT_GMAIL_APP_PASSWORD Actions secret is a dedicated Google app password, never the account password. It is available only to the mail/check steps; the preparation child never receives it. No connector session or another project's credential is exported into GitHub.

## Authorization

1. In the chosen Google account, enable 2-Step Verification if needed and open https://myaccount.google.com/apppasswords. Create a dedicated app password named EasyBosnian reports. Some account/security policies do not offer app passwords; report the actual blocker rather than bypassing it.
2. Save that password directly as REPORT_GMAIL_APP_PASSWORD at this exact private repository’s Actions secrets page. Keep it out of chat and files. Set the repository variable REPORT_EMAIL_TO to the same authorized Gmail address.
3. Leave SUCCESS_REPORT_EMAIL_ENABLED=false until the connection check passes. A manually dispatched pipeline mode=verify authenticates to Gmail over TLS when REPORT_EMAIL_TO is configured; it sends no mail and cannot prepare/render/publish. Existing provider/cloud-workspace checks stay intact.
4. After verification, set SUCCESS_REPORT_EMAIL_ENABLED=true. Subsequent successful daily runs send one report; no new schedule or automatic retry is added. Disable the variable to stop email without changing publication. Revoke/replace this dedicated password in Google and GitHub if needed.

Report/email errors are ancillary warnings: they do not rerun, undo or block completed publication. SMTP response prose and credentials are never logged. A timeout/ambiguous send is not retried. SMTP acceptance is reported honestly; it is not a guarantee that Gmail delivered to the inbox rather than Spam. Reports remain in the private artifact if email is disabled or fails. A completely missing run still produces no report/notification.

Google documents app-password requirements and setup at https://support.google.com/accounts/answer/185833 and its SMTP host/TLS configuration at https://support.google.com/a/answer/176600. This uses the existing Gmail account, standard-library SMTP and no paid service.
