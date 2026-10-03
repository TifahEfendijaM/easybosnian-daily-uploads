"""Failure artifacts and private GitHub issues; no heartbeat or missing-run monitor."""
from .core import ROOT, REPO, gh
from .http import redact

NEXT={
    'cloud ChatGPT authorization':'Complete a dedicated cloud-only ChatGPT sign-in and replace CODEX_AUTH_JSON privately.',
    'cloud ChatGPT credential persistence':'Check GH_SECRETS_TOKEN expiry and Secrets write access. Keep refreshed credentials private.',
    'cloud ChatGPT workspace verification':'Inspect the structured result and workspace probe, then rerun verify mode.',
    'cloud ChatGPT research/review':'Fix source access or incomplete review, then deliberately start daily mode. No automatic retry exists.',
    'validation':'Correct the reviewed content and preserve schema, history, quiz secrecy and measured-fit checks.',
    'Pillow rendering':'Shorten reviewed copy or fix typography; never truncate text or strip diacritics.',
    'FLUX generation':'Check the Cloudflare Free quota and model availability; no paid fallback exists.',
    'storage':'Check this project’s D1/KV access, free quota and image visibility.',
}


def failure(date,stage,error,publication,run_url=None):
    next_step=NEXT.get(stage,'Inspect the failed step and actual platform posts before manually running daily again; another run can publish duplicates.')
    text=f'Batch: {date}\nFailed stage: {stage}\nError: {redact(error)}\nPublication: {publication}\nRun/logs: {run_url or "No GitHub run exists for this invocation."}\nNext step: {next_step}\n'
    path=ROOT/'build/failure.txt';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    try: gh('issue','create','--repo',REPO,'--title',f'EasyBosnian {date}: {stage} failed','--body-file',str(path))
    except Exception as problem: text+='Failure notification issue could not be created: '+redact(problem)+'\n'
    path.write_text(text,encoding='utf-8');return text
