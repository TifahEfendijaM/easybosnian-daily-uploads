"""Ephemeral admin-only reports in the existing KV; never content history or a queue."""
import argparse
import json
import os
import re
from pathlib import Path

from .core import PROJECT, ROOT, private_github_outputs
from .http import SafeError
from .store import Store

REPORT_NAME=re.compile(r'(?:run-summary\.md|failure\.txt|preparation-result\.json|(?:b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})/(?:[a-z]+(?:-[a-z]+)*-result\.json|result\.json|report-source\.json|success-report\.(?:json|md|html)))')
MAX_BYTES=2_000_000


def report_path(run_id):
    if not re.fullmatch(r'[1-9][0-9]{0,19}',str(run_id)):
        raise ValueError('Invalid protected run identity')
    return '/v1/run-reports/'+str(run_id)


def validate_report(value,run_id):
    if (not isinstance(value,dict) or set(value)!={'project','run_id','mode','files'}
            or value['project']!=PROJECT or value['run_id']!=str(run_id)
            or value['mode'] not in ('verify','preview','daily') or not isinstance(value['files'],dict)
            or len(value['files'])>30
            or any(not REPORT_NAME.fullmatch(k) or not isinstance(v,str) for k,v in value['files'].items())
            or len(json.dumps(value,ensure_ascii=False).encode())>MAX_BYTES):
        raise ValueError('Invalid protected report')
    report_path(run_id)
    return value


def collect_report(run_id,mode):
    directory=ROOT/'build';files={}
    # Enumerate only top-level reports and one-level batch metadata. Never
    # traverse arbitrary directories or follow symlinks into credential files.
    for path in [*directory.glob('*'),*directory.glob('*/*')]:
        name=path.relative_to(directory).as_posix()
        if (REPORT_NAME.fullmatch(name) and path.is_file() and not path.is_symlink()
                and not path.parent.is_symlink() and path.stat().st_size<=MAX_BYTES):
            files[name]=path.read_text(encoding='utf-8')
    return validate_report({'project':PROJECT,'run_id':str(run_id),'mode':mode,'files':files},run_id)


def get_report(store,run_id):
    try:value=store.call('GET',report_path(run_id))
    except SafeError as error:
        if error.http_status==404:return None
        raise
    return validate_report(value,run_id)


def save_report(store,run_id,mode):
    value=collect_report(run_id,mode)
    result=store.call('PUT',report_path(run_id),value)
    if result.get('stored') is not True:raise ValueError('Protected run report not confirmed')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['save','fetch'])
    parser.add_argument('--run-id');args=parser.parse_args()
    rid=args.run_id or os.environ['GITHUB_RUN_ID']
    try:
        store=Store()
        if args.action=='save':
            if private_github_outputs():return
            save_report(store,rid,os.environ['MODE'])
            message='Detailed run report stored in authenticated private KV for 14 days; no public artifact or issue was created.'
            if os.getenv('GITHUB_STEP_SUMMARY'):
                with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write('\n'+message+'\n')
        else:
            value=get_report(store,rid)
            if value is None:raise ValueError('Protected run report missing or expired')
            # No extraction into caller-controlled paths; save one local JSON.
            destination=ROOT/'build'/('protected-run-'+str(rid)+'.json')
            destination.parent.mkdir(exist_ok=True)
            with destination.open('w',encoding='utf-8') as f:
                os.chmod(destination,0o600);json.dump(value,f,ensure_ascii=False,indent=2)
            message='Protected report downloaded to build/protected-run-'+str(rid)+'.json'
        print(message)
    except Exception:
        print('::warning::Protected report storage/read was not confirmed. No write or publication was repeated.')
        raise SystemExit(1) from None


if __name__=='__main__':main()
