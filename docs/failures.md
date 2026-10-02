# Where failures appear

Use a free Healthchecks account with email enabled. Configure three named checks in **Europe/Sarajevo**:

| Check | Expected signal | Grace |
|---|---|---|
| EasyBosnian preparation — GitHub queue save | 19:09 daily | 10 minutes |
| EasyBosnian pipeline — confirmed Instagram publication | 19:19 daily | 40 minutes |
| EasyBosnian monitoring | 19:59 daily | 15 minutes |

Preparation success means reviewed JSON was reserved, saved to the exact private repository and read back. Pipeline success means a verified Instagram permalink, or an explicitly selected unpublished preview. During initial authorization, leave live-post monitors paused until setup is ready. A monitor is not a scheduler and never retries work.

Store the preparation and pipeline ping URLs as `HC_PREPARATION_URL` and `HC_PIPELINE_URL` in repository secrets; the preparation URL is also in the local protected `.env`. Use `easybosnian set-worker-secret HC_WATCHDOG_URL` to save the watchdog ping URL directly to this Cloudflare Worker. Do not put ping URLs in chat, public files, or code. Subscribe to Actions failure emails and Watch → Custom → Issues for this exact private repository. Notification destinations are the Healthchecks account's verified email, GitHub account's configured notification email, and the private repository's Issues/Actions pages. No messages are sent to other people.

The setup command checks the preparation/pipeline pings, the Worker's exact private repository access, Actions read access, private issue creation and watchdog ping before setting monitoring ready. These are notification self-tests and do not generate images or publish. Successful provider responses confirm acceptance; check the verified email inboxes to confirm receipt. Setup does not require another publishing approval.

The Python runner's immediate failure report includes date/batch, exact failed stage, sanitized error, publication state, actual GitHub run/log link when available, and next action. It saves `build/failure.txt`, creates a private GitHub issue and sends a Healthchecks failure body. GitHub artifacts retain result JSON/cards/diagnostics for seven days; credentials and raw provider responses are excluded. Preparation failures before a workflow exists explicitly say no GitHub run exists; the scheduled task reports its result link when available.

Stages: ChatGPT preparation/queue save; validation; FLUX generation; Pillow rendering; storage; authorization; publishing; publication verification. Early checkout/dependency failures remain visible as exact GitHub step failures and native Actions email; their missing pipeline heartbeat is also reported by the independent monitor.

Publication status is one of: nothing published; published but verification pending; confirmed published; uncertain. Never interpret green CI as proof. The job summary and result JSON carry a permalink only after verification. An uncertain publishing response preserves its intent and requires `easybosnian pipeline --mode reconcile --date YYYY-MM-DD`. If there is no unambiguous matching post, inspect Instagram manually rather than repeating publication.

At 19:59, the monitoring-only Worker queries this exact repository's scheduled runs and Cloudflare batch state. It reports a missing package, missing scheduled run or unverified publication with the latest actual run link. The monitor's code cannot invoke generation, workflow dispatch or publishing. It deduplicates alerts per day/stage. If the Worker itself or GitHub never starts, Healthchecks independently detects the missing expected signal and emails you. Native GitHub email alone cannot detect a workflow that never ran.

KV is eventually consistent. A newly uploaded image may not be visible in another region immediately. The publishing pipeline verifies accessible bytes before container creation; a visibility/processing failure stops with its saved state. Deliberate reruns reuse stored work. KV expires images after 14 days; late reconciliation still checks published media, but old unposted asset recovery may require manual decisions. History/reservations never expire.

Free limits, revoked tokens, a sleeping computer and platform delays are reported honestly. Ten minutes is a target gap, not a completion guarantee. There is no scheduled retry.
