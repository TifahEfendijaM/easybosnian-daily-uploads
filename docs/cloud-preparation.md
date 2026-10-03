# Cloud preparation

The existing Cloudflare Worker dispatches preparation.yml at 05:00 Europe/Sarajevo with mode=daily. One ubuntu-22.04 job restores a dedicated cloud-only managed ChatGPT credential, runs the official pinned Codex CLI 0.160.0, saves reviewed content in D1, persists the refreshed credential and renders/publishes immediately afterward. No paid OpenAI API or awake Mac. There is no reusable workflow, queue commit, package handoff or recovery mode.

The research child uses a stripped environment, workspace-write sandbox, live web search, seven-minute limit, private logs, structured ready/blocked output schema and a tracked-file Git diff check. Provider/admin/GitHub secrets stay with the trusted wrapper. It can write unreviewed drafts/private research under build only. Free-form model output and raw events never go into issues or uploaded artifacts. The wrapper requires an actual reviewed draft and validates independently before saving history.

verify checks infrastructure and the child's actual workspace probe. It cannot choose content, write history, call FLUX, render or publish. Preview saves content if absent and otherwise reuses today's history; it renders privately. Daily always chooses replacement content against the complete current history and overwrites today's earlier row. Returned IDs/results are diagnostic artifacts, not saved publication gates.

Credential bootstrap/persistence retains the dedicated temporary auth directory and managed-subscription validation. The workflow's always-run persistence step saves refreshed CODEX_AUTH_JSON with the separate repository-restricted GH_SECRETS_TOKEN, even after preparation fails. Never copy a desktop session, expose a token or use stale auth as a paid fallback.

Use scripts/cloud_auth_setup.py login then save only if dedicated cloud authorization needs renewal. Existing configured credentials remain. The old cloud proof commit/read-back is removed because connection verification no longer needs repository content writes. Safe verification results are workflow artifacts.

DAILY_POSTING_ENABLED is checked before daily preparation and every actual live publisher. verify/preview remain available while disabled. Missing schedules generate no notification. Failures during a run still produce private GitHub issues and build/failure.txt; no Healthchecks or watchdog exists.

Content instructions live in docs/cloud-agent-task.md and docs/preparation-task.md. All learner-visible copy is Bosnian. Quiz photography must be relevant: a pictured object is allowed when identifying it is the task, while images must not solve a hidden fact or reveal a written answer/option letter. Znaš li? prioritizes useful situations, meaningful comparisons and verified interesting facts over routine grammar drills. Translation-template rejection is a deterministic backstop, not a general language detector; the GPT reviewer still checks every public string and scene.
