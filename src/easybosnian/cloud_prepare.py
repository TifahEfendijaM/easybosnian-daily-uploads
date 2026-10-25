"""Private, serialized ChatGPT preparation; never publishes or generates artwork."""
import argparse
import copy
import json
import os
import secrets
import subprocess
from pathlib import Path

from .cli import fit_check, prepare
from .core import PROJECT, REPO, ROOT, gh, read_json, today, verify_repository, write_json, require_publishing, RepositoryIdentityError
from .notify import failure
from .readiness import check_infrastructure
from .store import Store
from .validate import validate
from .selection import selection_context, check_selection, novelty_history, word_levels, quiz_format_target
from .levels import select_run_level
from .research_context import reading_instructions
from .batches import identity, plan_batch
from .codex_diagnostics import CodexExecutionError, execution_diagnostic


AGENT_FAILURES = {
    "repository_guard": "The research agent could not accept the wrapper's verified repository boundary; inspect the cloud task instructions.",
    "history_access": "The research agent could not read the complete private history context; check the runner's context file.",
    "research_sources": "Reliable source opening or Bosnian research was incomplete; review source access before deliberately running daily mode.",
    "semantic_novelty": "A ChatGPT-selected theme or word could not be verified as semantically new against history. Explicit custom and retained choices may repeat.",
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


class AgentIntegrityError(ValueError):
    """Tracked-file changes cannot be downgraded into a cosmetic-review fallback."""


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


def run_codex(prompt, timeout=420, *, result_contract=None, images=(), read_only=False):
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
    write_json(result_schema, result_contract or AGENT_RESULT_SCHEMA)
    args = ["codex", "exec", "--json", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--sandbox", "read-only" if read_only else "workspace-write", "--cd", str(ROOT), "--color", "never",
            "-c", 'approval_policy="never"', "-c", 'cli_auth_credentials_store="file"',
            "-c", "sandbox_workspace_write.network_access="+('false' if read_only else 'true'),
            "-c", 'web_search="disabled"' if read_only else 'web_search="live"',
            "--output-schema", str(result_schema), "--output-last-message", str(output)]
    for picture in images:
        picture = Path(picture).resolve()
        if not picture.is_relative_to((ROOT/'build').resolve()) or not picture.is_file():
            raise ValueError('Visual review images must be local generated build files')
        args.extend(['--image', str(picture)])
    args.append('-')
    diagnostic_path = ROOT / 'build/cloud-agent-diagnostics' / ('visual-result.json' if read_only else 'text-result.json')
    result = None
    timed_out = False
    with events.open("w", encoding="utf-8") as private_log:
        events.chmod(0o600)
        try:
            result = subprocess.run(args, input=prompt, text=True, env=child_env, cwd=ROOT,
                                    stdout=private_log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            raise ValueError("ChatGPT review exceeded its time allowance; inspect the run and reviewed content; no retry was dispatched") from None
        finally:
            try:
                private_log.flush()
                diagnostic = execution_diagnostic(events, None if result is None else result.returncode, timed_out=timed_out)
                write_json(diagnostic_path, diagnostic)
            finally:
                # Check even if execution or diagnostic recording failed, before any fallback.
                try:
                    verify_repository(remote=True)
                    changed = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
                except Exception:
                    raise AgentIntegrityError("Could not confirm the repository/file boundary after ChatGPT execution") from None
                if changed.stdout.strip():
                    raise AgentIntegrityError("Preparation changed tracked project files; refusing to save content")
    if output.exists():
        output.chmod(0o600)
    if result.returncode:
        raise CodexExecutionError(diagnostic)
    if not output.is_file():
        raise ValueError("Cloud ChatGPT ended without its required completion result; no batch was approved")
    return output.read_text(encoding="utf-8").strip()


def cloud_run(mode, selection='new', custom_theme='', custom_words=None, custom_actions=None, batch_target='latest', difficulty='random'):
    if mode not in ('verify','preview','daily'): raise ValueError('Unknown workflow mode')
    run_date=today();date=run_date;stage='cloud preparation infrastructure authorization'
    try:
        if mode=='daily': require_publishing()
        check_infrastructure();store=Store();history=store.history()
        if history.get('project')!=PROJECT: raise ValueError('History belongs to a different project')
        publication_ids=store.publications_for_date(run_date) if mode!='verify' and batch_target=='all_today' else []
        plan=plan_batch(history,run_date,batch_target,publication_batch_ids=[item['batch_id'] for item in publication_ids]) if mode!='verify' else None
        if plan:date=plan['date']
        chosen=selection_context(history,date,selection if mode=='daily' else 'new',custom_theme,custom_words,custom_actions,source_batch_id=plan['source_batch_id']) if plan else {'choice':'new','previous':None}
        reused=None
        from .selection import reused_kinds, frozen_kinds
        photo_kinds=reused_kinds(chosen) if mode=='daily' else ()
        fixed_kinds=frozen_kinds(chosen) if mode=='daily' else ()
        frozen_sources={}
        if photo_kinds:
            from .photo_reuse import prepare_photos
            stage='saved background retrieval'
            reused=prepare_photos(store,chosen['previous'],plan['source_batch_id'],plan['batch_id'],date,kinds=photo_kinds)
        if fixed_kinds:
            from .frozen_cards import prepare_cards
            stage='saved finished-card retrieval'
            frozen_sources=prepare_cards(store,chosen['previous'],plan['source_batch_id'],plan['batch_id'],date,
                                         fixed_kinds,reused['paths'])
        existing=next((x for x in history['days'] if identity(x)==plan['batch_id']),None) if plan else None
        saved_preview=mode=='preview' and existing and existing['content'].get('schema_version')==1
        level=(existing['content'].get('bosnian_level') if saved_preview else
               select_run_level(chosen,difficulty) if mode!='verify' else None)
        if level is not None:chosen['target_cefr']=level
        # Exact-cache snapshots are parent-owned provenance, not research/design
        # recommendations. Keep all published copy/novelty metadata in context.
        context_history=copy.deepcopy(history);context_selection=copy.deepcopy(chosen)
        for row in context_history['days']:
            if isinstance(row.get('content'),dict):row['content'].pop('rendered_sources',None)
        if context_selection.get('previous'):context_selection['previous'].pop('rendered_sources',None)
        write_json(ROOT/'build/preparation-context.json',{'history':context_history,'selection':context_selection,'target_cefr':level,
                                                       'batch_date':date,'run_date':run_date,'batch_target':batch_target,'batch':plan,
                                                       'reused_photo_kinds':list(photo_kinds),'frozen_card_kinds':list(fixed_kinds)})
        if mode=='verify':
            stage='cloud ChatGPT workspace verification';probe=ROOT/'build/cloud-file-probe.json';probe.unlink(missing_ok=True)
            require_agent_ready(run_codex(
                'Connection verification ONLY. The wrapper verified the exact pinned repository. '
                'Read AGENTS.md and docs/cloud-agent-task.md, then every bounded review-context page. '
                'Do not follow content preparation instructions, choose words, call provider APIs, '
                'write history, generate images or publish. Write exactly '
                '{"status":"ready","reason":"none"} to build/cloud-file-probe.json. '
                'Return that object only after the file exists. Do not inspect credentials or files '
                'outside this checkout.'+reading_instructions(read_json(ROOT/'build/preparation-context.json')),timeout=180))
            if not probe.is_file() or read_json(probe)!={'status':'ready','reason':'none'}:
                raise ValueError('ChatGPT did not write its required workspace probe')
            result={'date':date,'status':'cloud connection verified','private_history_read':True,
                    'chatgpt_workspace_read_write':True,'publication':'No content prepared, saved, rendered or published'}
        else:
            existing=next((x for x in history['days'] if identity(x)==plan['batch_id']),None)
            if mode=='preview' and existing and existing['content'].get('schema_version')==1:
                # Reuse published content privately; preview never writes history.
                package=dict(existing['content'],batch_id=plan['batch_id']);validate(package);fit_check(package)
            else:
                stage='cloud ChatGPT research/review';draft=ROOT/f'build/preparation/{date}.json';draft.unlink(missing_ok=True)
                # One independent, uniform draw for this research attempt. Do
                # not redraw after failure; genuinely binary questions use two.
                chosen['quiz_option_target']=(chosen['previous']['private_review'].get('quiz_choice_review',{}).get('target',
                                              len(chosen['previous']['cards'][0]['options'])) if 'quiz' in fixed_kinds else secrets.choice((2,3,4)))
                context=read_json(ROOT/'build/preparation-context.json')
                chosen['quiz_format_target']=quiz_format_target(chosen)
                for key in ('quiz_option_target','quiz_format_target'):context['selection'][key]=chosen[key]
                write_json(ROOT/'build/preparation-context.json',context)
                prompt=(ROOT/'docs/cloud-agent-task.md').read_text().replace('{{DATE}}',date)+reading_instructions(context)
                require_agent_ready(run_codex(prompt,**({'images':list(reused['paths'].values())} if reused else {})))
                if not draft.is_file(): raise ValueError('ChatGPT returned ready without creating the required draft')
                package=read_json(draft)
                if any(key in package for key in ('background_source','background_sources','rendered_sources')):
                    raise ValueError('Photo provenance must be assigned by the trusted wrapper')
                if fixed_kinds:
                    previous=chosen['previous']
                    for index,card in enumerate(previous['cards']):
                        if card['kind'] in fixed_kinds:
                            package['cards'][index]=copy.deepcopy(card)
                            package['words'][index]=copy.deepcopy(previous['words'][index])
                    if 'quiz' in fixed_kinds:
                        for key in ('correct_option','correct_text','explanation','answer_aliases','identifying_hints','quiz_choice_review'):
                            if key in previous['private_review']:package['private_review'][key]=copy.deepcopy(previous['private_review'][key])
                        if 'quiz_choice_review' not in package['private_review']:
                            package['private_review']['quiz_choice_review']={'target':chosen['quiz_option_target'],'binary':False,
                                'reason':'Answer count retained from the explicitly frozen, previously reviewed quiz.'}
                    package['rendered_sources']=frozen_sources
                if reused:
                    from .photo_reuse import seal_photos
                    package.update(seal_photos(reused,metadata=True))
                if package['date']!=date: raise ValueError('Draft has the wrong Sarajevo date')
                if package.get('batch_id',plan['batch_id'])!=plan['batch_id']:raise ValueError('Draft has the wrong batch identity')
                package['batch_id']=plan['batch_id'];write_json(draft,package)
                stage='validation';check_selection(package,chosen)
                validate(package,novelty_history(history,date,chosen,package),include_today=True,require_website_footer=True,require_quiz_format=True,require_caption_level=True,target_cefr=level,word_level_targets=word_levels(package,chosen,level),quiz_option_target=chosen['quiz_option_target'],require_language_policy=True);fit_check(package)
                stage='private content staging';prepare(draft,selection=chosen,batch_target=batch_target,run_date=run_date,plan=plan)
            from .cli import stage_content
            stage_content(package,root=ROOT)
            result={'date':date,'status':'reviewed content staged privately','mode':mode,
                    'publication':'nothing published by preparation'}
        result.update(project=PROJECT,mode=mode,run_date=run_date,batch_target=batch_target)
        if level is not None:result['target_cefr']=package.get('bosnian_level',level) if mode=='preview' else level
        if plan:result.update(batch_id=plan['batch_id'],cleanup_batch_id=plan['cleanup_batch_id'])
        if plan and batch_target=='all_today':
            result.update(cleanup_batch_ids=plan['cleanup_batch_ids'],prune_history_ids=plan['prune_history_ids'])
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
                  [os.getenv('CUSTOM_WORD_'+str(i)+'_ACTION','keep_today') for i in (1,2,3)],
                  batch_target=os.getenv('BATCH_TARGET','latest'),difficulty=os.getenv('DIFFICULTY','random'))
        return
    try:
        bootstrap() if action == "bootstrap" else persist()
    except Exception as error:
        stage=("repository verification" if isinstance(error,RepositoryIdentityError) else
               "cloud ChatGPT authorization" if action == "bootstrap" else "cloud ChatGPT credential persistence")
        print(failure(today(), stage,
                      error, "This credential step publishes nothing; inspect the separate pipeline run", os.getenv("GITHUB_RUN_URL")))
        raise RuntimeError("Cloud preparation stopped at "+stage+"; inspect the protected run report") from None


if __name__ == "__main__":
    main()
