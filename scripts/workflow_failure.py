"""Fallback issue/report for checkout/install failures before project imports work."""
import os
import json
from datetime import datetime
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

REPO='TifahEfendijaM/easybosnian-daily-uploads'
path=Path('build/failure.txt')
if not path.exists():
    stage=next((name for name in ['checkout','python','node','install','auth','preparation','artwork','persist','publication'] if os.getenv(name.upper()+'_OUTCOME')=='failure'),'workflow execution')
    path.parent.mkdir(exist_ok=True)
    date=datetime.now(ZoneInfo('Europe/Sarajevo')).date().isoformat()
    path.write_text(f'Batch: {date}\nFailed stage: {stage}\nError: GitHub step failed; inspect its logs.\nPublication: inspect this run’s platform result artifacts; no publication is claimed by this fallback.\nRun/logs: {os.getenv("GITHUB_RUN_URL","No GitHub run URL was supplied.")}\nNext step: inspect the failed step before deliberately starting daily again. No automatic retry exists.\n')
    if os.getenv('GITHUB_REPOSITORY')!=REPO:raise RuntimeError('Repository mismatch')
    identity=subprocess.run(['gh','api',f'repos/{REPO}'],capture_output=True,text=True)
    value=json.loads(identity.stdout) if not identity.returncode else {}
    if (value.get('full_name')!=REPO or value.get('id')!=1401814933
            or value.get('owner',{}).get('id')!=50710040 or value.get('default_branch')!='main'):
        raise RuntimeError('Exact pinned target unavailable')
    if value.get('private') is True and os.getenv('GITHUB_REPOSITORY_VISIBILITY')=='private':
        result=subprocess.run(['gh','issue','create','--repo',REPO,'--title',f'EasyBosnian {date}: {stage} failed','--body-file',str(path)],capture_output=True,text=True)
        if result.returncode:print('Failure issue could not be created; protected failure report remains available')
    else:
        print('No public issue created; failure details are included in the run Summary')
