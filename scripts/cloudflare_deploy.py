"""Deploy only this project's new resources using the user's authorized Wrangler login."""
import argparse
import json
import os
import re
import secrets
import subprocess
import time
import tomllib
from pathlib import Path

from easybosnian.core import ROOT, PROJECT, REPO, gh, verify_repository, write_json
from easybosnian.http import SafeError, request

NAME='easybosnian-daily-tifah-v1'
RUNTIME=Path('/Users/fatih_efe/.cache/codex-runtimes/codex-primary-runtime/dependencies')


def wrangler(*args,input_text=None):
    env=dict(os.environ)
    if (RUNTIME/'node/bin/node').exists():
        env['PATH']=str(RUNTIME/'node/bin')+os.pathsep+env['PATH']
        command=[str(RUNTIME/'bin/fallback/pnpm'),'dlx','wrangler@4.145.0',*args]
    else:
        command=['npx','--yes','wrangler@4.145.0',*args]
    result=subprocess.run(command,cwd=ROOT/'cloudflare',input=input_text,capture_output=True,text=True,env=env)
    if result.returncode:
        raise RuntimeError('Cloudflare command failed; check login, account permissions and free quotas')
    return result.stdout


def auth_token():
    # Captured in memory only; never returned to chat or written to a repository.
    return json.loads(wrangler('auth','token','--json'))['token']


def cf(token,account,method,path,data=None):
    return request(method,f'https://api.cloudflare.com/client/v4/accounts/{account}{path}',data,{'Authorization':'Bearer '+token})['result']


def save_local(name,value):
    path=ROOT/'.env'
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[x for x in lines if not x.startswith(name+'=')]
    lines.append(name+'='+value)
    path.write_text('\n'.join(lines)+'\n'); path.chmod(0o600)


def put_worker_secret(name,value):
    verify_repository(remote=True)
    if name not in ('NOTIFY_GITHUB_TOKEN','HC_WATCHDOG_URL'):
        raise ValueError('Only this project monitoring secrets are supported')
    if not value or any(c.isspace() for c in value):
        raise ValueError('Enter one complete credential without spaces')
    if name=='NOTIFY_GITHUB_TOKEN' and not value.startswith('github_pat_'):
        raise ValueError('Use the newly generated fine-grained GitHub token')
    if name=='HC_WATCHDOG_URL' and not re.fullmatch(r'https://hc-ping\.com/[a-f0-9-]{36}',value):
        raise ValueError('Use the private Healthchecks ping URL')
    state=json.loads((ROOT/'cloudflare/deployment.json').read_text())
    if state.get('project')!=PROJECT or not state.get('worker_deployed') or not state.get('free_workers_verified'):
        raise ValueError('This project free deployment has not been verified')
    config=tomllib.loads((ROOT/'cloudflare/wrangler.toml').read_text())
    if config.get('name')!=NAME or config.get('account_id')!=state['account_id']:
        raise ValueError('Worker configuration belongs to another project')
    if config.get('vars',{}).get('PROJECT_ID')!=PROJECT or config.get('vars',{}).get('GITHUB_REPOSITORY')!=REPO:
        raise ValueError('Worker project/repository identity mismatch')
    token=auth_token()
    actual=cf(token,state['account_id'],'GET',f'/workers/scripts/{NAME}/settings')
    bindings={b['name']:b for b in actual.get('bindings',[])}
    if bindings.get('DB',{}).get('id')!=state['database_id'] or bindings.get('IMAGES',{}).get('namespace_id')!=state['kv_id']:
        raise ValueError('Worker bindings do not match this project deployment')
    wrangler('secret','put',name,'--config','wrangler.toml',input_text=value)
    checked=cf(token,state['account_id'],'GET',f'/workers/scripts/{NAME}/settings')
    if not any(b.get('name')==name and b.get('type')=='secret_text' for b in checked.get('bindings',[])):
        raise ValueError('Cloudflare did not confirm the monitoring secret binding')
    print(name+' saved privately to this project Worker; no post was made')


def deploy(account,free_confirmed=False,free_evidence=None):
    verify_repository(remote=True)
    if not re.fullmatch('[a-f0-9]{32}',account): raise ValueError('Invalid Cloudflare account ID')
    token=auth_token()
    try:
        subscriptions=cf(token,account,'GET','/subscriptions')
    except Exception:
        if not free_confirmed and not free_evidence: raise ValueError('Billing access unavailable: verify the Workers Free plan before deploying') from None
        subscriptions=[]
    paid_workers=[s for s in subscriptions if 'workers' in str(s.get('rate_plan',{})).lower() and s.get('rate_plan',{}).get('id') not in ('workers_free','free')]
    if paid_workers: raise ValueError('This account has a paid Workers subscription; use a Workers Free account before deployment')
    # Persist only newly created resource IDs. Never find/reuse an old project's database.
    state_path=ROOT/'cloudflare/deployment.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'project':PROJECT,'account_id':account}
    if state['project']!=PROJECT or state['account_id']!=account: raise ValueError('Deployment state belongs to a different project/account')
    # Check this exact new name before creating resources or uploading code. A name
    # collision must never overwrite another Worker, even in the same account.
    try:
        existing=cf(token,account,'GET',f'/workers/scripts/{NAME}/settings')
    except SafeError as error:
        if not str(error).startswith('HTTP 404;'): raise
        existing=None
    if existing is not None:
        if not state.get('worker_deployed'):
            raise ValueError('The new Worker name already exists without a verified deployment record; stop and reconcile instead of overwriting it')
        bindings={item['name']:item for item in existing.get('bindings',[])}
        if bindings.get('DB',{}).get('id')!=state.get('database_id') or bindings.get('IMAGES',{}).get('namespace_id')!=state.get('kv_id'):
            raise ValueError('Worker bindings do not match this project deployment record')
    if not state.get('database_id'):
        database=cf(token,account,'POST','/d1/database',{'name':NAME})
        state['database_id']=database['uuid']; write_json(state_path,state)
    if not state.get('kv_id'):
        namespace=cf(token,account,'POST','/storage/kv/namespaces',{'title':NAME+'-images'})
        state['kv_id']=namespace['id']; write_json(state_path,state)
    config=(ROOT/'cloudflare/wrangler.example.toml').read_text()
    config=config.replace('REPLACE_WITH_NEW_DATABASE_ID',state['database_id']).replace('REPLACE_WITH_NEW_NAMESPACE_ID',state['kv_id'])
    config='account_id = "'+account+'"\n'+config
    (ROOT/'cloudflare/wrangler.toml').write_text(config)
    for sql in (ROOT/'cloudflare/migrations/0001.sql').read_text().split(';'):
        if sql.strip(): cf(token,account,'POST',f'/d1/database/{state["database_id"]}/query',{'sql':sql})
    # Official deploy validates syntax and bindings. No provider generation or publication is run.
    output=wrangler('deploy','--config','wrangler.toml')
    match=re.search(r'https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev',output)
    if not match: raise ValueError('Cloudflare did not return a deployed workers.dev endpoint')
    url=match.group(0)
    state.update(worker_url=url,worker_deployed=True)
    write_json(state_path,state)
    admin_path=ROOT/'.env'
    local=admin_path.read_text().splitlines() if admin_path.exists() else []
    existing=next((line.split('=',1)[1] for line in local if line.startswith('EASYBOSNIAN_ADMIN_TOKEN=')),None)
    admin=existing or secrets.token_urlsafe(48)
    wrangler('secret','put','ADMIN_TOKEN','--config','wrangler.toml',input_text=admin)
    gh('secret','set','EASYBOSNIAN_ADMIN_TOKEN','--repo',REPO,input_text=admin)
    gh('secret','set','EASYBOSNIAN_WORKER_URL','--repo',REPO,input_text=url)
    save_local('EASYBOSNIAN_ADMIN_TOKEN',admin); save_local('EASYBOSNIAN_WORKER_URL',url)
    # A new workers.dev route can briefly return 404 while deployment propagates.
    # This checks availability only; it never starts or retries content generation.
    for attempt in range(5):
        try:
            info=request('GET',url+'/health')
            break
        except SafeError as error:
            if attempt==4 or not str(error).startswith('HTTP 404;'): raise
            time.sleep(2)
    if info.get('project')!=PROJECT: raise ValueError('Deployed project identity check failed')
    history=request('GET',url+'/v1/history',headers={'Authorization':'Bearer '+admin})
    if history.get('project')!=PROJECT: raise ValueError('Private history check failed')
    state.update(worker_url=url,free_workers_verified=True,free_plan_evidence=free_evidence or 'account subscriptions or explicit user confirmation')
    write_json(state_path,state)
    print(json.dumps({'deployed':url,'project':PROJECT,'history_batches':len(history['batches']),'daily_posting':'waiting for Instagram and monitoring authorization'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--account',required=True); parser.add_argument('--free-confirmed',action='store_true'); parser.add_argument('--free-plan-evidence')
    args=parser.parse_args(); deploy(args.account,args.free_confirmed,args.free_plan_evidence)
