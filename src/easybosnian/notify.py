import os
from pathlib import Path

from .core import REPO, gh
from .http import redact, request

NEXT = {
    "preparation/queue save": "Inspect the ChatGPT task result, repository access and reserved history; prepare a reviewed package, then deliberately run the existing batch.",
    "validation": "Correct the unqueued package or reconcile the immutable queued package with the reviewer; do not bypass answer/history checks.",
    "FLUX generation": "Check the Cloudflare Free quota and model status; deliberately rerun this batch to reuse existing backgrounds.",
    "Pillow rendering": "Review text fit and fonts; rewrite copy through a reviewed replacement process, never truncate.",
    "storage": "Check Cloudflare KV/D1 quotas, Worker authorization and asset visibility; inspect saved batch state before rerunning.",
    "authorization": "Reauthorize @easy_bosnian privately and replace the relevant GitHub secret; verify account identity.",
    "publishing": "Inspect Instagram and saved container IDs. Run reconcile; do not resend a publish request while its outcome is uncertain.",
    "publication verification": "Run reconcile and inspect the account's recent posts; a successful request or green workflow is not verified publication.",
    "scheduling": "Inspect Actions and ChatGPT Scheduled. Check access, disabled schedules and free quotas; no automatic retry is configured."
}


def heartbeat(name, status="success", message=""):
    url = os.environ.get("HC_" + name.upper() + "_URL")
    if not url:
        raise RuntimeError("Missing free external dead-man monitor: " + name)
    suffix = {"success": "", "start": "/start", "fail": "/fail"}[status]
    request("POST", url.rstrip("/") + suffix, redact(message).encode(), raw=True, timeout=20)


def failure(date, stage, error, publication, run_url=None):
    text = f"Batch: {date}\nFailed stage: {stage}\nError: {redact(error)}\nPublication: {publication}\nRun/logs: {run_url or 'No GitHub run exists; inspect ChatGPT Scheduled for its result.'}\nNext step: {NEXT.get(stage, NEXT['scheduling'])}\n"
    Path("build").mkdir(exist_ok=True)
    Path("build/failure.txt").write_text(text, encoding="utf-8")
    try:
        gh("issue", "create", "--repo", REPO, "--title", f"EasyBosnian {date}: {stage} failed", "--body-file", "build/failure.txt")
    except Exception as problem:
        text += "Failure notification issue could not be created: " + redact(problem) + "\n"
    Path("build/failure.txt").write_text(text, encoding="utf-8")
    return text
