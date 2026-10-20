"""Failure artifacts and private GitHub issues; no heartbeat or missing-run monitor."""
from .core import ROOT, REPO, gh
from .http import redact

NEXT={
    'cloud ChatGPT authorization':'Complete a dedicated cloud-only ChatGPT sign-in and replace CODEX_AUTH_JSON privately.',
    'cloud ChatGPT credential persistence':'Check GH_SECRETS_TOKEN expiry and Secrets write access. Keep refreshed credentials private.',
    'cloud ChatGPT workspace verification':'Inspect the structured result and workspace probe, then rerun verify mode.',
    'cloud ChatGPT research/review':'Fix source access or incomplete review, then deliberately start daily mode. No automatic retry exists.',
    'validation':'Correct the reviewed content and preserve schema, history, quiz secrecy and measured-fit checks.',
    'Instagram poll validation':'Review the quiz/caption limits. Oversized answers publish unchanged without a poll; caption overflow requires a reviewed rewrite.',
    'Instagram poll attachment':'The carousel is already published. Inspect its native poll and the run artifact; do not republish just to repair the poll. Meta add-ons cannot be edited after publication.',
    'Pillow rendering':'Shorten reviewed copy or fix typography; never truncate text or strip diacritics.',
    'FLUX generation':'Check the Cloudflare Free quota and model availability; no paid fallback exists.',
    'storage':'Check this project’s D1/KV access, free quota and image visibility.',
}


def next_step(stage,error):
    if getattr(error,'reason',None)=='instagram_publishing_limit':
        return 'Instagram reports its publishing allowance is exhausted or insufficient for all three Stories. Wait for its rolling quota to recover before a deliberate new run. Another workflow run does not reset the allowance. No automatic retry, delayed upload or catch-up is scheduled; confirmed feed posts and Facebook Stories remain published.'
    if stage.startswith('Facebook '):
        return 'Check the exact Easy Bosnian Page authorization, pages_show_list/pages_read_engagement/pages_manage_posts and current can_post capability. Renew the separate FACEBOOK_PAGE_TOKEN without removing existing Instagram permissions. No publishing retry is sent.'
    if stage=='FLUX generation':
        code=getattr(error,'provider_code',None)
        if code==3036:
            return 'Cloudflare reports the daily free allocation is exhausted. It resets at 00:00 UTC; reduce preview usage. No paid fallback or automatic retry is sent.'
        if code==3040:
            return 'Cloudflare reports temporary inference capacity exhaustion. Check Workers AI service status before deliberately starting another run; no automatic retry is sent.'
        if code in (3007,3008) or getattr(error,'provider_http_status',None)==408:
            return 'Cloudflare inference timed out or was aborted. Check Workers AI service status and inspect saved artwork before deliberately starting another run; no automatic retry is sent.'
        if getattr(error,'provider_http_status',None)==409:
            return 'Cloudflare returned an upstream conflict, not a confirmed quota error. Inspect this run’s protected provider diagnostic and current Workers AI status; no automatic retry or paid fallback is sent.'
        if code==5035:
            return 'Cloudflare reports a paid-plan-only model. Check that this Worker uses the approved Free FLUX.1 Schnell model; do not upgrade or use a paid fallback.'
        if getattr(error,'reason',None) in ('cache_read_failed','cache_write_failed'):
            return 'Check this project’s private Workers KV binding, access and free storage limits; no generation or write retry is sent.'
        if getattr(error,'reason',None)=='ai_binding_missing':
            return 'Restore the AI binding on this project’s existing Worker; no inference request was sent.'
        if code in (5018,5016,3023,3041,5007,3042,3003,5019,5004,5005,3039,3006):
            return 'Check the approved model ID, Workers AI binding, account access and request limits against the reported Cloudflare code; no automatic retry or paid fallback is sent.'
    return NEXT.get(stage,'Inspect the failed step and actual platform posts before manually running daily again; another run can publish duplicates.')


def failure(date,stage,error,publication,run_url=None):
    action=next_step(stage,error)
    text=f'Batch: {date}\nFailed stage: {stage}\nError: {redact(error)}\nPublication: {publication}\nRun/logs: {run_url or "No GitHub run exists for this invocation."}\nNext step: {action}\n'
    path=ROOT/'build/failure.txt';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    try: gh('issue','create','--repo',REPO,'--title',f'EasyBosnian {date}: {stage} failed','--body-file',str(path))
    except Exception as problem: text+='Failure notification issue could not be created: '+redact(problem)+'\n'
    path.write_text(text,encoding='utf-8');return text
