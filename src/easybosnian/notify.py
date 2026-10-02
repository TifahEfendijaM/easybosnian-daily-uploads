import os
from pathlib import Path

from .core import REPO, gh
from .http import redact, request
from .store import Store

NEXT = {
    "Facebook authorization": "Privately reauthorize only the EasyBosnian Page with pages_show_list, pages_read_engagement and pages_manage_posts; verify its saved Page ID and long-lived Page token.",
    "Facebook publishing": "Inspect the EasyBosnian Page and saved Facebook post/photo IDs. Use read-only Facebook reconciliation; do not repeat an uncertain publication request.",
    "Facebook photo upload": "Inspect the saved unpublished Facebook photo IDs and upload intents. An uncertain upload must not be blindly repeated.",
    "Facebook publication verification": "Use read-only Facebook reconciliation; check the exact Page, caption, three photo IDs and actual permalink.",
    "Facebook validation": "Inspect the immutable reviewed batch and handed-off hash; never bypass history or quiz secrecy checks.",
    "Facebook storage": "Check this project's private Cloudflare assets and temporary public final-image URLs. Reuse the saved artwork.",
    "Instagram Stories authorization": "Verify @easy_bosnian and its Instagram Login content-publishing authorization; do not reuse Facebook Page credentials.",
    "Instagram Stories validation": "Stories wait for the exact daily Instagram carousel to be independently verified; inspect its saved publication result.",
    "Instagram Stories publishing": "Inspect each saved Story container, publish intent and media ID. Reconcile known IDs read-only; never repost a Story with an uncertain response.",
    "Instagram Stories verification": "Check saved Story IDs on @easy_bosnian and their Story permalinks. Use read-only reconciliation; Highlights require manual addition in Instagram.",
    "Instagram Stories rendering": "Reuse the exact published slides, padded to 1080×1920 without cropping or changing text; inspect private storage and measured fit.",
    "cloud preparation infrastructure authorization": "Inspect the read-only infrastructure check in this exact repository. Verify private Cloudflare access, Instagram identity, and repository-restricted credential persistence access. Do not change content reservations or dispatch publication.",
    "cloud ChatGPT authorization": "Complete a fresh dedicated cloud-only Codex browser login, store CODEX_AUTH_JSON privately in this exact repository, then run the connection check. Do not copy the desktop session or use a paid API fallback.",
    "cloud ChatGPT credential persistence": "Check the repository-restricted GH_SECRETS_TOKEN expiry and Secrets write access. Reseed the cloud-only ChatGPT sign-in if updated credentials were lost; never restore stale tokens or dispatch publishing automatically.",
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


def heartbeat(name, status="success", message="", force=False):
    if not force and Store().call("GET", "/v1/config").get("healthchecks_deferred") is True:
        return "deferred by user; GitHub failure reporting remains active"
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
