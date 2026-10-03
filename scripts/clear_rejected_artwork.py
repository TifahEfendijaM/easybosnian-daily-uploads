"""One-time authorized cleanup, before migration, of the rejected October 3 artwork."""
import importlib.util
import json
import re
import tomllib
from urllib.parse import quote,urlencode
from easybosnian.cli import load_env
from easybosnian.core import ROOT,PROJECT,REPO,verify_repository,write_json
from easybosnian.store import Store

DATE='2026-10-03'
REJECTED='759bd137b4b4ed33a37a7efdda952925ef345e8c31aa40c78f4754980e493f7a'


def main():
    verify_repository(remote=True);load_env()
    spec=importlib.util.spec_from_file_location('deployment',ROOT/'scripts/cloudflare_deploy.py')
    deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)
    state=json.loads((ROOT/'cloudflare/deployment.json').read_text())
    config=tomllib.loads((ROOT/'cloudflare/wrangler.toml').read_text())
    if state['project']!=PROJECT or not state.get('free_workers_verified') or config['name']!=deploy.NAME or config['account_id']!=state['account_id'] or config['vars']['GITHUB_REPOSITORY']!=REPO:
        raise ValueError('Exact existing Free project identity required')
    token=deploy.auth_token();account=state['account_id'];namespace=state['kv_id']
    bindings={x['name']:x for x in deploy.cf(token,account,'GET',f'/workers/scripts/{deploy.NAME}/settings')['bindings']}
    if bindings['DB']['id']!=state['database_id'] or bindings['IMAGES']['namespace_id']!=namespace or bindings['PREPARATION_DISPATCH_ENABLED']['text']!='false':
        raise ValueError('Existing storage bindings and paused external start required')
    record=Store().call('GET',f'/v1/batches/{DATE}')
    if record.get('hash')!=REJECTED: raise ValueError('Current date content is not the explicitly rejected package; refuse cleanup')
    keys=set()
    for prefix in (f'private:{DATE}:',f'private-ai:{DATE}:'):
        values=deploy.cf(token,account,'GET',f'/storage/kv/namespaces/{namespace}/keys?'+urlencode({'prefix':prefix,'limit':1000}))
        if len(values)>=1000:raise ValueError('Incomplete exact-date artwork listing')
        for item in values:
            if not item['name'].startswith(prefix):raise ValueError('Cross-date key returned')
            keys.add(item['name'])
    def urls(value):
        if isinstance(value,dict):
            for item in value.values():urls(item)
        elif isinstance(value,list):
            for item in value:urls(item)
        elif isinstance(value,str):
            match=re.fullmatch(re.escape(state['worker_url'])+r'/images/([a-f0-9]{64})\.jpg',value)
            if match:keys.add('public:'+match[1])
    urls(record['state'])
    for key in sorted(keys):deploy.cf(token,account,'DELETE',f'/storage/kv/namespaces/{namespace}/values/'+quote(key,safe=''))
    report={'date':DATE,'repository':REPO,'deleted_artwork_keys':len(keys),'history_unchanged_until_migration':True,'social_posts_deleted':False}
    write_json(ROOT/'build/rejected-artwork-cleanup.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':main()
