"""Explicit one-time import of known IDs into one identified private batch."""
import argparse
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

from easybosnian.cli import load_env
from easybosnian.core import REPO, gh, verify_repository
from easybosnian.batches import BATCH_ID, identity
from easybosnian.store import Store


def collect(files, date, instagram_id, facebook_id, tiktok_id):
    result=[]
    def add(platform,kind,object_id,account):
        if object_id:result.append((date,platform,kind,str(object_id),str(account)))
    for name,raw in files.items():
        p=json.loads(raw)
        if p.get('batch')!=date:raise ValueError('Artifact date differs from requested date')
        if name=='instagram-result.json':add('instagram','feed',p.get('media_id'),instagram_id)
        elif name=='facebook-result.json':
            add('facebook','feed',p.get('post_id'),facebook_id)
            for object_id in p.get('photo_ids',[]):add('facebook','photo',object_id,facebook_id)
        elif name=='tiktok-result.json':add('tiktok','feed',p.get('post_id'),tiktok_id)
        elif name=='instagram-stories-result.json':
            for item in p.get('stories',[]):add('instagram','story',item.get('media_id'),instagram_id)
        elif name=='facebook-stories-result.json':
            for item in p.get('stories',[]):
                add('facebook','photo',item.get('photo_id'),facebook_id)
                add('facebook','story',item.get('post_id'),facebook_id)
    return list(dict.fromkeys(result))


def import_scope(files,date,history,batch_id=None):
    reported={json.loads(raw).get('batch_id') for raw in files.values()}-{None}
    if len(reported)>1:raise ValueError('Artifacts contain multiple batch identities')
    if reported:
        actual=next(iter(reported))
        if batch_id and batch_id!=actual:raise ValueError('Artifact batch differs from requested batch')
        batch_id=actual
    candidates=[identity(row) for row in history['days'] if row['date']==date]
    if not batch_id:
        if len(candidates)!=1:raise ValueError('Legacy artifact date is ambiguous; supply --batch-id explicitly')
        batch_id=candidates[0]
    if not BATCH_ID.fullmatch(batch_id) or batch_id not in candidates:
        raise ValueError('No matching saved batch for the artifact date/identity')
    return batch_id


def main():
    load_env();parser=argparse.ArgumentParser();parser.add_argument('--run',required=True,type=int);parser.add_argument('--date',required=True);parser.add_argument('--batch-id')
    args=parser.parse_args()
    run=json.loads(gh('api',f'repos/{REPO}/actions/runs/{args.run}'))
    if run.get('repository',{}).get('full_name')!=REPO or run.get('head_branch')!='main' or run.get('conclusion')!='success' or run.get('path')!='.github/workflows/preparation.yml':
        raise ValueError('Choose the exact successful main daily run in this repository')
    artifacts=json.loads(gh('api',f'repos/{REPO}/actions/runs/{args.run}/artifacts'))['artifacts']
    selected=[x for x in artifacts if x['name']==f'easybosnian-daily-{args.run}' and not x['expired']]
    if len(selected)!=1:raise ValueError('No unique current daily artifact exists')
    verify_repository(remote=True)
    result=subprocess.run(['gh','api',f'repos/{REPO}/actions/artifacts/{selected[0]["id"]}/zip'],capture_output=True,check=True)
    files={};allowed={'instagram-result.json','facebook-result.json','tiktok-result.json','instagram-stories-result.json','facebook-stories-result.json'}
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
        if sum(x.file_size for x in archive.infolist())>25_000_000:raise ValueError('Artifact exceeds the bounded private import size')
        for item in archive.infolist():
            name=Path(item.filename).name
            if name not in allowed:continue
            if name in files:raise ValueError('Ambiguous diagnostic filenames')
            files[name]=archive.read(item)
    records=collect(files,args.date,os.environ['INSTAGRAM_USER_ID'],os.environ['FACEBOOK_PAGE_ID'],os.environ['BUFFER_TIKTOK_CHANNEL_ID'])
    if not records:raise ValueError('No returned provider identifiers found')
    store=Store()
    batch_id=import_scope(files,args.date,store.history(),args.batch_id)
    for date,platform,kind,object_id,account_id in records:store.remember(batch_id,platform,kind,object_id,account_id)
    actual=store.publications(batch_id)
    if any(not any(x['platform']==p and x['kind']==k and x['object_id']==i and x['account_id']==a for x in actual) for d,p,k,i,a in records):
        raise ValueError('Stored identifiers could not be confirmed')
    print(f'Imported and read back {len(records)} batch-specific provider identifiers. No content history or social posts changed.')


if __name__=='__main__':main()
