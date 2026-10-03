# Where failures appear

The user explicitly deferred Healthchecks on 2026-10-02 until Instagram works. During this phase, protected configuration records `healthchecks_deferred: true` and independently verified `github_monitoring_ready: true`; `monitoring_ready` stays false. Preparation, pipeline and watchdog skip Healthchecks requests. Immediate failures and the 11:59 Worker monitor still create private GitHub issues, with private Actions logs/artifacts available for both cloud preparation and publishing. Email receipt is not claimed. If the monitoring Worker itself never starts, its missing signal cannot yet be detected through Healthchecks; that remaining coverage is deferred, not reported as complete.

Use a free Healthchecks account with email enabled. When resuming the deferred Healthchecks setup, configure three named checks in **Europe/Sarajevo**. The saved deferred Healthchecks definitions still require updating; the active Worker already checks at 11:59:

| Check | Expected signal | Grace |
|---|---|---|
| EasyBosnian preparation — GitHub queue save | 10:00 daily | 10 minutes |
| EasyBosnian pipeline — confirmed Instagram publication | Successful preparation (immediate handoff) | 40 minutes |
| EasyBosnian monitoring | 11:59 daily | 15 minutes |

Preparation success means reviewed JSON was reserved, saved to the exact private repository and read back. Pipeline success means a verified Instagram permalink, or an explicitly selected unpublished preview. During initial authorization, leave live-post monitors paused until setup is ready. A monitor is not a scheduler and never retries work.

Store the preparation and pipeline ping URLs as `HC_PREPARATION_URL` and `HC_PIPELINE_URL` in repository secrets; both are also in the local protected `.env` for notification verification. Use `easybosnian set-worker-secret HC_WATCHDOG_URL` to save the watchdog ping URL directly to this Cloudflare Worker. Do not put ping URLs in chat, public files, or code. Confirm the Healthchecks email integration separately from signing in; the integration must be assigned to all three checks and confirmed before notification self-tests. Subscribe to Actions failure emails and Watch → Custom → Issues for this exact private repository. Notification destinations are the Healthchecks account's verified email, GitHub account's configured notification email, and the private repository's Issues/Actions pages. No messages are sent to other people.

The setup command checks the preparation/pipeline pings, the Worker's exact private repository access, Actions read access, private issue creation and watchdog ping before setting monitoring ready. These are notification self-tests and do not generate images or publish. Successful provider responses confirm acceptance; check the verified email inboxes to confirm receipt. Setup does not require another publishing approval.

The Python runner's immediate failure report includes date/batch, exact failed stage, sanitized error, publication state, actual GitHub run/log link when available, and next action. It saves `build/failure.txt`, creates a private GitHub issue and sends a Healthchecks failure body. GitHub artifacts retain result JSON/cards/diagnostics for seven days; credentials and raw provider responses are excluded. Preparation failures before a workflow exists explicitly say no GitHub run exists; the scheduled task reports its result link when available.

Stages: ChatGPT preparation/queue save; validation; FLUX generation; Pillow rendering; storage; authorization; publishing; publication verification. Early checkout/dependency failures remain visible as exact GitHub step failures and native Actions email; their missing pipeline heartbeat is also reported by the independent monitor.

Publication status is one of: nothing published; published but verification pending; confirmed published; uncertain. Never interpret green CI as proof. The job summary and result JSON carry a permalink only after verification. An uncertain publishing response preserves its intent and requires `easybosnian pipeline --mode reconcile --date YYYY-MM-DD`. If there is no unambiguous matching post, inspect Instagram manually rather than repeating publication.

At 11:59, the monitoring-only Worker queries this exact repository's external dispatch record and recover_today workflow_dispatch preparation runs and Cloudflare batch state. Each daily run contains preparation and reusable publication jobs. It also monitors the armed first schedule while publication remains disabled pending the first real package. It reports a missing package, missing preparation run or unverified completion-based publication with the latest actual run link. The monitor's code cannot invoke generation, workflow dispatch or publishing. It deduplicates alerts per day/stage. If the Worker itself or GitHub never starts, Healthchecks independently detects the missing expected signal and emails you. Native GitHub email alone cannot detect a workflow that never ran.

KV is eventually consistent. A newly uploaded image may not be visible in another region immediately. The publishing pipeline verifies accessible bytes before container creation; a visibility/processing failure stops with its saved state. Deliberate reruns reuse stored work. KV expires images after 14 days; late reconciliation still checks published media, but old unposted asset recovery may require manual decisions. History/reservations never expire.

Free limits, revoked tokens, ChatGPT subscription limits and platform delays are reported honestly. Publication follows successful preparation immediately; runner queues can add startup delay. There is no scheduled retry.
