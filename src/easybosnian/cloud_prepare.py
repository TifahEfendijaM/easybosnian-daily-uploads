"""Private, serialized ChatGPT preparation; never publishes or generates artwork."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from .cli import fit_check, prepare
from .core import PROJECT, REPO, ROOT, gh, read_json, today, verify_repository, write_json, require_publishing
from .notify import failure
from .readiness import check_infrastructure
from .store import Store
from .validate import validate
from .selection import selection_context, check_selection, novelty_history
from .levels import load_level


AGENT_FAILURES = {
    "repository_guard": "The research agent could not accept the wrapper's verified repository boundary; inspect the cloud task instructions.",
    "history_access": "The research agent could not read the complete private history context; check the runner's context file.",
    "research_sources": "Reliable source opening or Bosnian research was incomplete; review source access before deliberately running daily mode.",
    "semantic_novelty": "The theme or words could not be verified as semantically new against all history content.",
    "text_fit": "The reviewed text did not pass measured fit; revise the unreserved draft without truncation.",
    "quiz_secrecy": "The answer-secrecy review did not pass; revise the unreserved draft before saving it.",
    "design_review": "The shared palette, card layouts or FLUX prompt review was incomplete.",
    "file_access": "The research agent could not read or write its permitted workspace files; inspect the cloud file-access check.",
    "validation": "The research agent could not validate the unreserved draft; inspect the package contract and validation tools.",
    "auth_or_usage": "The research agent reported an authentication or subscription usage block; verify the dedicated cloud sign-in and limits.",
    "other": "The research agent did not complete the required review; no draft was approved and nothing was published.",
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
            raise ValueError("ChatGPT review exceeded its time allowance; inspect the run and reviewed content; no retry was dispatched") from None
    if output.exists():
        output.chmod(0o600)
    if result.returncode:
        raise ValueError("Cloud ChatGPT execution failed: verify the dedicated sign-in and ChatGPT usage limits; no paid fallback")
    verify_repository(remote=True)
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    if changed.stdout.strip():
        raise ValueError("Preparation changed tracked project files; refusing to save content")
    if not output.is_file():
        raise ValueError("Cloud ChatGPT ended without its required completion result; no batch was approved")
    return output.read_text(encoding="utf-8").strip()


def cloud_run(mode, selection='new', custom_theme='', custom_words=None, custom_actions=None):
    if mode not in ('verify','preview','daily'): raise ValueError('Unknown workflow mode')
    date=today();stage='cloud preparation infrastructure authorization'
    try:
        if mode=='daily': require_publishing()
        check_infrastructure();store=Store();history=store.history()
        if history.get('project')!=PROJECT: raise ValueError('History belongs to a different project')
        chosen=selection_context(history,date,selection if mode=='daily' else 'new',custom_theme,custom_words,custom_actions) if mode!='verify' else {'choice':'new','previous':None}
        level=load_level()
        write_json(ROOT/'build/preparation-context.json',{'history':history,'selection':chosen,'target_cefr':level})
        if mode=='verify':
            stage='cloud ChatGPT workspace verification';probe=ROOT/'build/cloud-file-probe.json';probe.unlink(missing_ok=True)
            require_agent_ready(run_codex(
                'Connection verification ONLY. The wrapper verified the exact private repository. '
                'Read AGENTS.md, docs/cloud-agent-task.md and all build/preparation-context.json. '
                'Do not follow content preparation instructions, choose words, call provider APIs, '
                'write history, generate images or publish. Write exactly '
                '{"status":"ready","reason":"none"} to build/cloud-file-probe.json. '
                'Return that object only after the file exists. Do not inspect credentials or files '
                'outside this checkout.',timeout=180))
            if not probe.is_file() or read_json(probe)!={'status':'ready','reason':'none'}:
                raise ValueError('ChatGPT did not write its required workspace probe')
            result={'date':date,'status':'cloud connection verified','private_history_read':True,
                    'chatgpt_workspace_read_write':True,'publication':'No content prepared, saved, rendered or published'}
        else:
            existing=next((x for x in history['days'] if x['date']==date),None)
            if mode=='preview' and existing:
                # User chose saved previews; no claim that this content was published.
                package=existing['content'];validate(package,history);fit_check(package)
            else:
                stage='cloud ChatGPT research/review';draft=ROOT/f'build/preparation/{date}.json';draft.unlink(missing_ok=True)
                prompt=(ROOT/'docs/cloud-agent-task.md').read_text().replace('{{DATE}}',date)
                require_agent_ready(run_codex(prompt))
                if not draft.is_file(): raise ValueError('ChatGPT returned ready without creating the required draft')
                package=read_json(draft)
                if package['date']!=date: raise ValueError('Draft has the wrong Sarajevo date')
                stage='validation';check_selection(package,chosen)
                fresh=chosen['choice']!='same_words'
                validate(package,novelty_history(history,date,chosen),include_today=True,require_website_footer=fresh,require_quiz_format=fresh,target_cefr=level if fresh else None);fit_check(package)
                stage='preparation/history save';prepare(draft,selection=chosen)
            result={'date':date,'status':'reviewed content available in private history','mode':mode,
                    'publication':'nothing published by preparation'}
        write_json(ROOT/'build/preparation-result.json',result);print(json.dumps(result,indent=2));return result
    except Exception as error:
        print(failure(date,stage,error,'nothing published by this preparation step',os.getenv('GITHUB_RUN_URL')))
        raise RuntimeError('Cloud preparation failed at '+stage) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "verify", "preview", "daily", "persist"])
    action = parser.parse_args().action
    if action in ("verify", "preview", "daily"):
        cloud_run(action,os.getenv('CONTENT_SELECTION','new'),os.getenv('CUSTOM_THEME',''),
                  [os.getenv('CUSTOM_WORD_'+str(i),'') for i in (1,2,3)],
                  [os.getenv('CUSTOM_WORD_'+str(i)+'_ACTION','keep_today') for i in (1,2,3)])
        return
    try:
        bootstrap() if action == "bootstrap" else persist()
    except Exception as error:
        print(failure(today(), "cloud ChatGPT authorization" if action == "bootstrap" else "cloud ChatGPT credential persistence",
                      error, "This credential step publishes nothing; inspect the separate pipeline run", os.getenv("GITHUB_RUN_URL")))
        raise RuntimeError("Dedicated cloud sign-in failed; inspect the private issue and run") from None


if __name__ == "__main__":
    main()
