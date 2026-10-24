# Cloud preparation

The existing Worker dispatches preparation.yml at 05:00 Europe/Sarajevo into one ubuntu-22.04 job using the official pinned Codex CLI and dedicated cloud-only subscription credential. No paid API or awake Mac is required.

Current policies have one owner per stage:

- Research entry point/output/checks: `cloud-agent-task.md`.
- Selection, novelty, editorial copy, natural scene prompts and captions: `preparation-task.md`.
- Per-run CEFR, custom actions/corrections and field languages: `difficulty-policy.md`.
- Approved post-photo design choices and Pillow checks: `visual-style-contract.md`.
- Photo inspection, bounded attempts, element recovery and exact retained cards: `element-design-recovery.md`.
- Modes, history, credentials, hosting, account checks, publishing, cleanup, diagnostics and reports: `pipeline-operations.md`.

Execution remains research → independently validated private staging → photo generation/inspection → declarative visual review/Pillow rendering → private credential persistence → independently gated publication → confirmed-feed history save. Exact pinned-card/photo reuse follows its selected action. Verify is connection/workspace-only; preview stays private and never writes history. Service failures are not retried; only defect/rejection feedback permits the bounded photo/design attempts in the recovery policy.

The research child has a stripped environment, workspace-write sandbox, live source-opening web research, seven-minute limit, structured ready/blocked output and tracked-file diff guard. It can write only unreviewed build drafts/private notes. Provider/admin/GitHub credentials remain with the parent. Visual/photo-inspection children are read-only/tool-free. Original CLI JSONL traces/model output remain private; safe envelope-derived diagnostics alone enter artifacts.

The workflow always privately persists refreshed CODEX_AUTH_JSON using the separate repository-restricted GH_SECRETS_TOKEN, including after preparation failure. Live exposure/publication requires persistence success. Renew the dedicated authorization only when needed with scripts/cloud_auth_setup.py login then save; do not copy desktop auth, commit a proof file or add a paid fallback. No separate reusable workflow, queue package or recovery mode exists. Detailed current invariants and rollout instructions are in pipeline-operations.md; historical deployment notes do not override them.

Research reads use `python -m easybosnian.research_context index` and numbered bounded pages, with every retained/imported batch and exact historical teaching copy/semantic metadata. Old source citations, audit checklists/notes and cache references are omitted only from the research view; selected previous content and the original validation context remain complete. Full unabridged pages remain available. The wrapper supplies the page counts to research and verify prompts. No history is erased, shortened, reserved or saved by this local reader; it makes no API/model calls and adds no retry.
