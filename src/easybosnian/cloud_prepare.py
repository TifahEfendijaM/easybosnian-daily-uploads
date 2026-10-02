"""Private, serialized ChatGPT preparation; never publishes or generates artwork."""
import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

from .cli import activate, fit_check, prepare
from .core import PROJECT, REPO, ROOT, digest, gh, read_json, today, verify_repository, write_json, publication_monitoring_ready
from .notify import failure
from .readiness import check_infrastructure
from .store import Store
from .validate import validate


AGENT_FAILURES = {
    "repository_guard": "The research agent could not accept the wrapper's verified repository boundary; inspect the cloud task instructions.",
    "history_access": "The research agent could not read the complete private history and queue context; check the runner's context file.",
    "research_sources": "Reliable source opening or Bosnian research was incomplete; review source access before deliberately recovering the batch.",
    "semantic_novelty": "The theme or words could not be verified as semantically new against all history and queued content.",
    "text_fit": "The reviewed text did not pass measured fit; revise the unreserved draft without truncation.",
    "quiz_secrecy": "The answer-secrecy review did not pass; revise the unreserved draft before saving it.",
    "design_review": "The shared palette, card layouts or FLUX prompt review was incomplete.",
    "file_access": "The research agent could not read or write its permitted workspace files; inspect the cloud file-access check.",
    "validation": "The research agent could not validate the unreserved draft; inspect the package contract and validation tools.",
    "auth_or_usage": "The research agent reported an authentication or subscription usage block; verify the dedicated cloud sign-in and limits.",
    "other": "The research agent did not complete the required review; no draft was approved and no publishing handoff was emitted.",
}
AGENT_RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["status", "reason"],
    "properties": {
        "status": {"enum": ["ready", "blocked"]},
        "reason": {"enum": ["none", *AGENT_FAILURES]},
    },
}


def require_agent_ready(text):
    # Never put free-form model output, quiz answers or raw events in an issue/log.
    try:
        result = json.loads(text)
        if not isinstance(result, dict) or set(result) != {"status", "reason"}:
            raise ValueError()
        if result["status"] == "ready" and result["reason"] == "none":
            return
        if result["status"] != "blocked" or result["reason"] not in AGENT_FAILURES:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("ChatGPT returned no valid completion result; check the cloud result contract. No batch was approved.") from None
    raise ValueError(AGENT_FAILURES[result["reason"]])


def managed_auth(text):
    try:
        value = json.loads(text)
        tokens = value.get("tokens") or {}
        if value.get("auth_mode") != "chatgpt" or value.get("OPENAI_API_KEY"):
            raise ValueError()
        if not all(isinstance(tokens.get(k), str) and tokens[k] for k in ("access_token", "refresh_token", "id_token")):
            raise ValueError()
        if not value.get("last_refresh"):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Cloud preparation needs a dedicated managed ChatGPT sign-in; paid API keys are refused") from None
    return value


def auth_file():
    directory = Path(os.environ["EASYBOSNIAN_CODEX_DIR"]).resolve()
    # This is a dedicated Codex credential directory, never the desktop app's session.
    expected = Path(os.environ["RUNNER_TEMP"]).resolve() / "easybosnian-cloud-codex"
    if directory != expected:
        raise ValueError("Cloud auth directory must be this runner's dedicated temporary directory")
    return directory / "auth.json"


def bootstrap():
    verify_repository(remote=True)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Cloud runner required")
    secret = os.environ.get("CODEX_AUTH_JSON", "")
    managed_auth(secret)
    path = auth_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)


def persist():
    path = auth_file()
    if not path.exists():
        raise ValueError("No cloud credential file exists; sign in again privately")
    updated = path.read_text(encoding="utf-8")
    managed_auth(updated)
    original = os.environ.get("GH_TOKEN")
    try:
        os.environ["GH_TOKEN"] = os.environ["GH_SECRETS_TOKEN"]
        gh("secret", "set", "CODEX_AUTH_JSON", "--repo", REPO, input_text=updated)
        listed = json.loads(gh("api", f"repos/{REPO}/actions/secrets/CODEX_AUTH_JSON"))
        if listed.get("name") != "CODEX_AUTH_JSON":
            raise ValueError("Refreshed cloud credential secret was not confirmed")
    finally:
        if original is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = original
    path.unlink()
    print("Managed ChatGPT credentials saved privately for the next serialized cloud run")


def queued_packages():
    listing = json.loads(gh("api", f"repos/{REPO}/contents/queue?ref=main"))
    if len(listing) >= 1000:
        raise ValueError("Private queue listing reached GitHub's directory limit; add complete tree pagination before choosing content")
    packages = []
    for entry in listing:
        if entry["type"] != "file" or not entry["name"].endswith(".json"):
            continue
        if entry["path"] != "queue/" + entry["name"]:
            raise ValueError("Invalid private queue path")
        saved = json.loads(gh("api", f"repos/{REPO}/contents/{entry['path']}?ref=main"))
        packages.append(json.loads(base64.b64decode(saved["content"])))
    return packages


def save_proof(proof):
    path = "docs/cloud-preparation-proof.json"
    payload = {"message": "Verify private cloud ChatGPT preparation connection", "branch": "main",
               "content": base64.b64encode((json.dumps(proof, indent=2) + "\n").encode()).decode()}
    listing = json.loads(gh("api", f"repos/{REPO}/contents/docs?ref=main"))
    existing = next((x for x in listing if x["path"] == path), None)
    if existing:
        payload["sha"] = existing["sha"]
    gh("api", f"repos/{REPO}/contents/{path}", "--method", "PUT", "--input", "-", input_text=json.dumps(payload))
    saved = json.loads(gh("api", f"repos/{REPO}/contents/{path}?ref=main"))
    if json.loads(base64.b64decode(saved["content"])) != proof:
        raise ValueError("Cloud GitHub write/read-back proof does not match")


def run_codex(prompt, timeout=420):
    path = auth_file()
    managed_auth(path.read_text(encoding="utf-8"))
    # Provider/admin/GitHub/Instagram credentials are only available to the trusted wrapper.
    allowed = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")
    child_env = {k: v for k, v in os.environ.items() if k in allowed}
    child_env["CODEX_HOME"] = str(path.parent)
    child_env["GITHUB_REPOSITORY"] = REPO
    output = ROOT / "build/cloud-agent-last.secret"
    events = ROOT / "build/cloud-agent-events.secret"
    events.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    output.unlink(missing_ok=True)
    result_schema = ROOT / "build/cloud-agent-result-schema.json"
    write_json(result_schema, AGENT_RESULT_SCHEMA)
    args = ["codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--sandbox", "workspace-write", "--cd", str(ROOT), "--color", "never",
            "-c", 'approval_policy="never"', "-c", 'cli_auth_credentials_store="file"',
            "-c", "sandbox_workspace_write.network_access=true", "-c", 'web_search="live"',
            "--output-schema", str(result_schema), "--output-last-message", str(output), "-"]
    with events.open("w", encoding="utf-8") as private_log:
        events.chmod(0o600)
        try:
            result = subprocess.run(args, input=prompt, text=True, env=child_env, cwd=ROOT,
                                    stdout=private_log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError("ChatGPT review exceeded its time allowance; inspect the run and reserved package; no retry was dispatched") from None
    if output.exists():
        output.chmod(0o600)
    if result.returncode:
        raise ValueError("Cloud ChatGPT execution failed: verify the dedicated sign-in and ChatGPT usage limits; no paid fallback")
    verify_repository(remote=True)
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    if changed.stdout.strip():
        raise ValueError("Preparation changed tracked project files; refusing to reserve content")
    if not output.is_file():
        raise ValueError("Cloud ChatGPT ended without its required completion result; no batch was approved")
    return output.read_text(encoding="utf-8").strip()


def publication_state(history, date):
    batch = next((x for x in history["batches"] if x["date"] == date), None)
    state = (batch or {}).get("state") or {}
    if state.get("verified"):
        return "already verified published"
    if state.get("publish_intent") or state.get("media_id"):
        return "publication uncertain; reconcile existing batch"
    return "nothing published by preparation; inspect the separate pipeline run"


def cloud_run(mode):
    date = today()
    publication = "nothing published by this preparation run"
    stage = "cloud preparation infrastructure authorization"
    try:
        check_infrastructure()
        store = Store()
        history = store.history()
        if history.get("project") != PROJECT:
            raise ValueError("Private Cloudflare history belongs to a different project")
        publication = publication_state(history, date)
        config = store.call("GET", "/v1/config")
        if not publication_monitoring_ready(config):
            raise ValueError("Required failure reporting setup has not been verified")
        queue = queued_packages()
        write_json(ROOT / "build/preparation-context.json", {"history": history, "queued_packages": queue})
        if mode == "verify":
            stage = "cloud ChatGPT workspace verification"
            probe = ROOT / "build/cloud-file-probe.json"
            probe.unlink(missing_ok=True)
            require_agent_ready(run_codex(
                "Connection verification ONLY. The trusted wrapper already verified the exact private "
                "TifahEfendijaM/easybosnian-daily-uploads repository; do not run Git/GitHub operations. "
                "Read local AGENTS.md, docs/cloud-agent-task.md and all build/preparation-context.json. "
                "Do not follow the content-preparation task in this verification: do not choose words, "
                "research a theme, prepare/reserve content, call provider APIs or publish. "
                "Use a workspace file tool to write exactly {\"status\":\"ready\",\"reason\":\"none\"} "
                "to build/cloud-file-probe.json. Return that same object only after confirming the file "
                "exists. If reading/writing fails, return status blocked with reason file_access. "
                "Do not inspect credentials or files outside this checkout.", timeout=180))
            if not probe.is_file() or read_json(probe) != {"status": "ready", "reason": "none"}:
                raise ValueError("ChatGPT claimed completion without writing its workspace probe; no content was prepared")
            proof = {"repository": REPO, "project": PROJECT, "date": date,
                     "run_url": os.environ["GITHUB_RUN_URL"], "chatgpt_authenticated": True,
                     "private_history_read": True, "queued_packages_read": len(queue),
                     "chatgpt_workspace_read_write": True,
                     "publication": "No content prepared, reserved, generated or published by this connection check"}
            save_proof(proof)
            result = {**proof, "github_write_readback": True}
        else:
            reserved = next((x for x in history["batches"] if x["date"] == date), None)
            if reserved and (reserved.get("state") or {}).get("verified"):
                result = {"date": date, "status": "already verified published; preparation unchanged"}
            else:
                draft = ROOT / f"build/preparation/{date}.json"
                if reserved:
                    write_json(draft, store.batch(date)["package"])
                else:
                    stage = "cloud ChatGPT research/review"
                    draft.unlink(missing_ok=True)
                    prompt = (ROOT / "docs/cloud-agent-task.md").read_text().replace("{{DATE}}", date)
                    require_agent_ready(run_codex(prompt))
                    if not draft.is_file():
                        raise ValueError("ChatGPT claimed review completion without creating the required same-date draft; no batch was reserved")
                package = read_json(draft)
                if package["date"] != date:
                    raise ValueError("Reviewed draft has the wrong Sarajevo date")
                stage = "validation"
                validate(package, history)
                fit_check(package)
                stage = "preparation/queue save"
                prepare(draft)
                activate("enable-daily")
                enabled = store.call("GET", "/v1/config")
                if not enabled.get("daily_enabled") or not enabled.get("preparation_verified"):
                    raise ValueError("Scheduled publication activation read-back failed")
                result = {"date": date, "status": "reviewed JSON saved and read back", "package_hash": digest(package),
                          "queue_url": f"https://github.com/{REPO}/blob/main/queue/{date}.json",
                          "publication": publication, "scheduled_pipeline_enabled": True}
        write_json(ROOT / "build/preparation-result.json", result)
        print(json.dumps(result, indent=2))
    except Exception as error:
        # Codex output is kept private and never copied into failures, issues or artifacts.
        report = failure(date, stage, error, publication, os.getenv("GITHUB_RUN_URL"))
        print(report)
        raise RuntimeError("Cloud preparation failed; inspect the private run and failure issue") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "verify", "prepare", "persist"])
    action = parser.parse_args().action
    if action in ("verify", "prepare"):
        cloud_run(action)
        return
    try:
        bootstrap() if action == "bootstrap" else persist()
    except Exception as error:
        print(failure(today(), "cloud ChatGPT authorization" if action == "bootstrap" else "cloud ChatGPT credential persistence",
                      error, "This credential step publishes nothing; inspect the separate pipeline run", os.getenv("GITHUB_RUN_URL")))
        raise RuntimeError("Dedicated cloud sign-in failed; inspect the private issue and run") from None


if __name__ == "__main__":
    main()
