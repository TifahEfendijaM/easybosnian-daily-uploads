"""Exact finished-card reuse through private, expiring asset snapshots only."""
import copy
import hashlib
import io
import json
import os
import re
import uuid
import zipfile
from datetime import date
from pathlib import Path

from PIL import Image
from .batches import BATCH_ID
from .core import PROJECT,REPO,ROOT,gh,gh_binary,read_json,write_json
from .photo_reuse import KINDS


def digest(body):return hashlib.sha256(body).hexdigest()
def card_digest(card):return digest(json.dumps(card,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())


def checked_jpeg(body,size):
    if not isinstance(body,bytes) or not 100<=len(body)<=3_000_000:raise ValueError('Invalid saved card image size')
    with Image.open(io.BytesIO(body)) as image:
        if image.format!='JPEG' or image.size!=size:raise ValueError('Saved card image has the wrong format or dimensions')
        image.verify()


def checked_source(source,card):
    from .visual_diagnostics import approved_proposal
    from .visual_policy import safe_policy
    from .hybrid import roles
    from .core import ROOT as catalogue_root
    keys={'cache_id','date','card_sha256','story_sha256','content_sha256','metrics','policy'}
    if (not isinstance(source,dict) or set(source)!=keys or not isinstance(source['cache_id'],str)
            or not BATCH_ID.fullmatch(source['cache_id']) or source['cache_id'].startswith('legacy-')
            or not isinstance(source['date'],str)):
        raise ValueError('Invalid saved finished-card reference')
    try:
        if date.fromisoformat(source['date']).isoformat()!=source['date']:raise ValueError()
    except ValueError:raise ValueError('Invalid saved finished-card date') from None
    if any(not isinstance(source[k],str) or not re.fullmatch('[a-f0-9]{64}',source[k]) for k in ('card_sha256','story_sha256','content_sha256')):
        raise ValueError('Invalid saved finished-card fingerprint')
    if source['content_sha256']!=card_digest(card):raise ValueError('Saved finished card does not match its exact source text')
    metrics=source['metrics'];plan=metrics.get('composition') if isinstance(metrics,dict) else None
    if (approved_proposal(plan) is None or [b['role'] for b in plan['blocks']]!=roles(card)
            or metrics.get('size')!=[1080,1350]
            or metrics.get('palette') not in read_json(catalogue_root/'data/design-palettes.json')
            or metrics.get('design')!=plan['design']
            or metrics.get('block_styles')!={b['role']:b['style'] for b in plan['blocks']}):
        raise ValueError('Invalid saved finished-card rendering metadata')
    for key,minimum in (('heading_contrast',3),('body_contrast',4.5),('example_contrast',4.5)):
        score=metrics.get(key)
        if key=='example_contrast' and not card.get('example'):continue
        if type(score) not in (int,float) or not minimum<=score<=21:raise ValueError('Saved finished card lacks verified readable text')
    safe_policy(source['policy'],plan)
    return copy.deepcopy(source)


def snapshot(store,package,card,asset,policy):
    """A random private cache namespace is not a history batch or publication state."""
    feed=asset['path'].read_bytes();story=asset['story_path'].read_bytes()
    checked_jpeg(feed,(1080,1350));checked_jpeg(story,(1080,1920))
    source={'cache_id':'b-'+uuid.uuid4().hex,'date':package['date'],'card_sha256':digest(feed),
            'story_sha256':digest(story),'content_sha256':card_digest(card),
            'metrics':copy.deepcopy(asset['metrics']),'policy':copy.deepcopy(policy)}
    checked_source(source,card)
    # Existing admin-only staged asset API; both writes keep its 14-day TTL.
    for suffix,body in (('card',feed),('story',story)):
        store.call('PUT',f"/v1/private/batches/{source['cache_id']}/{card['kind']}-{suffix}.jpg",body,
                   headers={'Content-Type':'image/jpeg','X-EasyBosnian-Content-Date':source['date']})
    return source


def legacy_artifact(store,previous,source_batch_id,card,photo):
    """Old rows need exact re-render proof plus a recorded confirmed feed ID.

    Never trust mutable private filenames, a similar title or the newest zip.
    If the original renderer cannot reproduce the bytes, refuse rather than guess.
    """
    from .hybrid import render_hybrid
    from .stories import story_image
    from .visual_policy import policy_metadata
    from .core import ROOT as catalogue_root
    publications=store.publications(source_batch_id)
    known={platform:{str(item['object_id']) for item in publications
                    if item.get('kind')=='feed' and item.get('platform')==platform}
           for platform in ('instagram','facebook','tiktok')}
    if not any(known.values()):raise ValueError('No confirmed source can establish the saved finished card')
    runs=json.loads(gh('run','list','--repo',REPO,'--workflow','preparation.yml','--limit','30',
                      '--json','databaseId,displayTitle,status'))
    folder=ROOT/'build/frozen-card-import';folder.mkdir(parents=True,exist_ok=True)
    original=folder/(card['kind']+'-background.jpg')
    with Image.open(photo) as image:image.convert('RGB').save(original,'JPEG',quality=95)
    for run in runs:
        if run.get('status')!='completed' or run.get('displayTitle')!='EasyBosnian (daily)':continue
        rid=run['databaseId']
        if type(rid) is not int or rid<=0:continue
        archives=json.loads(gh('api',f'repos/{REPO}/actions/runs/{rid}/artifacts'))['artifacts']
        archive=next((a for a in archives if a['name']==f'easybosnian-daily-{rid}' and not a['expired'] and a['size_in_bytes']<=20_000_000),None)
        if not archive:continue
        raw=gh_binary('api',f"repos/{REPO}/actions/artifacts/{archive['id']}/zip")
        if len(raw)>20_000_000:continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            prefix=source_batch_id+'/'
            names={m.filename:m for m in z.infolist() if m.file_size<=3_000_000}
            required=[prefix+'image-placement-result.json',prefix+card['kind']+'-card.jpg']
            if any(n not in names for n in required):continue
            confirmed=False
            for platform,field in (('instagram','media_id'),('facebook','post_id'),('tiktok','post_id')):
                name=prefix+platform+'-result.json'
                if name not in names:continue
                publication=json.loads(z.read(name))
                if publication.get('published') is True and str(publication.get(field)) in known[platform]:confirmed=True
            if not confirmed:continue
            placement=json.loads(z.read(required[0]))
            if placement.get('batch_id')!=source_batch_id:continue
            choice=placement['cards'][card['kind']];plan=choice.get('composition')
            if not isinstance(plan,dict):continue
            feed=z.read(required[1]);path=folder/(card['kind']+'-card.jpg')
            try:metrics=render_hybrid(card,choice['palette'],original,path,plan,
                                      refined_panels=choice.get('render_policy',{}).get('version',0)>=9)
            except ValueError:continue
            if path.read_bytes()!=feed:continue
            story_path=folder/(card['kind']+'-story.jpg')
            story_image(path,story_path,read_json(catalogue_root/'data/design-palettes.json')[choice['palette']],original,card,
                        category_style=metrics['category_style'])
            old_story=prefix+card['kind']+'-story.jpg'
            if old_story in names and story_path.read_bytes()!=z.read(old_story):continue
            policy=choice.get('render_policy') or policy_metadata(plan,panel_opacity=100)
            return snapshot(store,previous,card,{'path':path,'story_path':story_path,'metrics':metrics},policy),{'card':path,'story':story_path}
    raise ValueError('Exact saved card could not be proven from retained publication artifacts; no replacement was generated')


def prepare_cards(store,previous,source_batch_id,batch_id,content_date,kinds,photos):
    sources={};files={}
    folder=ROOT/'build/frozen-cards';folder.mkdir(parents=True,exist_ok=True)
    for card in previous['cards']:
        kind=card['kind']
        if kind not in kinds:continue
        source=previous.get('rendered_sources',{}).get(kind)
        imported=None
        if source is None:source,imported=legacy_artifact(store,previous,source_batch_id,card,photos[kind])
        source=checked_source(source,card);sources[kind]=source;files[kind]={}
        for suffix,size in (('card',(1080,1350)),('story',(1080,1920))):
            raw=(imported[suffix].read_bytes() if imported else
                 store.call('GET',f"/v1/private/batches/{source['cache_id']}/{kind}-{suffix}.jpg",raw=True,
                            headers={'X-EasyBosnian-Content-Date':source['date']}))
            checked_jpeg(raw,size)
            if digest(raw)!=source[suffix+'_sha256']:raise ValueError('Saved finished card bytes differ from the verified source')
            path=folder/f'{kind}-{suffix}.jpg';path.write_bytes(raw);path.chmod(0o600);files[kind][suffix]=str(path)
    if set(sources)!=set(kinds):raise ValueError('Saved finished cards are incomplete')
    manifest={'project':PROJECT,'run_url':os.getenv('GITHUB_RUN_URL'),'batch_id':batch_id,'date':content_date,
              'sources':sources,'files':files}
    path=ROOT/'build/frozen-cards.secret';write_json(path,manifest);path.chmod(0o600)
    return sources


def loaded_cards(package):
    manifest=read_json(ROOT/'build/frozen-cards.secret')
    if any(manifest.get(k)!=v for k,v in {'project':PROJECT,'run_url':os.getenv('GITHUB_RUN_URL'),
           'batch_id':package['batch_id'],'date':package['date']}.items()):raise ValueError('Frozen cards belong to another workflow or batch')
    result={}
    for kind,source in manifest['sources'].items():
        if kind not in KINDS or source!=package.get('rendered_sources',{}).get(kind):raise ValueError('Frozen card reference changed after preparation')
        card=next(c for c in package['cards'] if c['kind']==kind);source=checked_source(source,card)
        entry={'source':source}
        for suffix,size in (('card',(1080,1350)),('story',(1080,1920))):
            path=Path(manifest['files'][kind][suffix]).resolve()
            if not path.is_relative_to((ROOT/'build/frozen-cards').resolve()):raise ValueError('Frozen card path escaped its private folder')
            body=path.read_bytes();checked_jpeg(body,size)
            if digest(body)!=source[suffix+'_sha256']:raise ValueError('Frozen card changed after preparation')
            entry[suffix]=path
        result[kind]=entry
    return result
