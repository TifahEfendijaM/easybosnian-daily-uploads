"""Publish reviewed Instagram Stories with separate photo/text treatment B."""
from .batches import output_key
import os
import shutil
from urllib.parse import urlparse
from PIL import Image, ImageFilter, ImageOps
from .core import ROOT, read_json, require_publishing, write_json
from .http import SafeError, request, redact
from .instagram_quota import publishing_quota,require_story_capacity
from .meta import Instagram
from .notify import failure
from .story_layouts import tall_story_image
from .store import wait_for_image

HIGHLIGHTS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}


def artwork_palette(package,assets,kind=None):
    if kind is None:  # Backward-compatible helper for old shared-palette callers.
        choices={asset.get('metrics',{}).get('palette',package['design_palette']) for asset in assets.values()}
        if len(choices)!=1:raise ValueError('Select a specific card for its final palette')
        selected=choices.pop()
    else:selected=assets[kind].get('metrics',{}).get('palette',package['design_palette'])
    catalogue=read_json(ROOT/'data/design-palettes.json')
    if selected not in catalogue:raise ValueError('Unknown prepared artwork palette')
    return catalogue[selected]


def story_image(source,destination,palette,background=None,card=None,category_style='rounded'):
    if card:
        return tall_story_image(card,background,destination,palette,category_style=category_style)
    with Image.open(source) as image:
        if image.size!=(1080,1350): raise ValueError('Story source must be the 1080×1350 published card')
        card=image.convert('RGB')
        # Fill only the outside space; the foreground retains every glyph/logo.
        if background:
            with Image.open(background) as original: fill=original.convert('RGB')
        else: fill=card.copy()
        canvas=ImageOps.fit(fill,(1080,1920),method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(48))
        canvas=Image.blend(canvas,Image.new('RGB',canvas.size,palette['scrim']),0.28)
        fitted=ImageOps.contain(card,(1080,1420),method=Image.Resampling.LANCZOS)
        canvas.paste(fitted,((1080-fitted.width)//2,(1920-fitted.height)//2))
        canvas.save(destination,'JPEG',quality=94,subsampling=0,optimize=True)


def prepared_story(asset,path,palette,card,renderer):
    source=asset.get('story_path')
    if source is not None:
        from .frozen_cards import checked_jpeg
        checked_jpeg(source.read_bytes(),(1080,1920))
        if source.resolve()!=path.resolve():shutil.copyfile(source,path)
    else:
        renderer(asset['path'],path,palette,asset.get('background_path'),card,
                 category_style=asset.get('metrics',{}).get('category_style','rounded'))


def verify_story(ig,media_id):
    actual=ig.story_media(media_id)
    if actual.get('id')!=media_id or actual.get('media_type')!='IMAGE' or actual.get('media_product_type')!='STORY':
        raise ValueError('Instagram returned a different Story media item')
    if not any(str(s.get('id'))==media_id for s in ig.stories().get('data',[])):
        raise ValueError('Story is not visible on @easy_bosnian')
    url=urlparse(actual.get('permalink',''))
    if url.scheme!='https' or url.hostname!='www.instagram.com' or not url.path.startswith('/stories/'):
        raise ValueError('Instagram returned no actual Story permalink')
    return actual['permalink']


def publish_stories(store,package,assets,record=None):
    date=package['date'];stage='Instagram Stories authorization';stories=[];containers=[]
    publication='nothing published to Instagram Stories';quota=None
    try:
        require_publishing()
        if os.getenv('INSTAGRAM_STORIES_ENABLED')!='true': raise ValueError('Story publisher is disabled')
        ig=Instagram();ig.refresh_if_needed();ig.verify_account()
        stage='Instagram Stories publishing quota';quota=publishing_quota(ig,required=len(package['cards']))
        require_story_capacity(quota)
        if quota['status']=='unavailable':
            print('::warning::Instagram publishing quota could not be read; no capacity is assumed; normal one-attempt publishing continues')
        for card in package['cards']:
            kind=card['kind'];palette=artwork_palette(package,assets,kind);stage='Instagram Stories rendering'
            path=ROOT/'build'/output_key(package)/f'{kind}-story.jpg'
            prepared_story(assets[kind],path,palette,card,story_image)
            body=path.read_bytes();stage='Instagram Stories storage'
            store.put_file(output_key(package),path.name,body);url=store.expose(output_key(package),path.name,body)
            wait_for_image(url,body,fetch=request)
            stage='Instagram Stories container creation';require_publishing();container=ig.story(url)
            diagnostic={'slide':kind,'container_id':container};containers.append(diagnostic)
            stage='Instagram Stories readiness';diagnostic['ready_status']=ig.ready(container,stable=True)
            stage='Instagram Stories publishing';require_publishing()
            publication='partial or uncertain Instagram Story publication'
            media_id=ig.publish(container)
            if record: record('story',media_id,ig.user_id)
            item={'slide':kind,'media_id':media_id,'highlight':HIGHLIGHTS[kind],'highlight_status':'manual addition required'}
            stories.append(item);stage='Instagram Stories verification';item['permalink']=verify_story(ig,media_id)
        result={'batch':date,'batch_id':package.get('batch_id'),'published':True,'status':'three image Stories confirmed published; Highlights need manual addition','stories':stories,'publishing_quota':quota}
        write_json(ROOT/'build'/output_key(package)/'instagram-stories-result.json',result);return result
    except Exception as error:
        quota_failure=getattr(error,'reason',None)=='instagram_publishing_limit'
        quota_conflict=bool(quota_failure and quota and quota['status']=='available'
                            and quota['remaining']>=quota['required'])
        if quota_failure:
            publication=f'{len(stories)} Instagram Stories confirmed; publishing-limit refusal; remaining Stories not published'
        if containers and stage=='Instagram Stories publishing':
            try:
                containers[-1]['status_after_failure']=ig.call('GET',containers[-1]['container_id'],{'fields':'status_code'}).get('status_code')
            except Exception:
                containers[-1]['status_readback']='unavailable; no retry'
        write_json(ROOT/'build'/output_key(package)/'instagram-stories-result.json',{'batch':date,'batch_id':package.get('batch_id'),'status':publication,'stories':stories,'containers':containers,'failed_stage':stage,
                   'failure_reason':'instagram_publishing_limit' if quota_failure else 'publisher_failed',
                   'error':redact(error),'publishing_quota':quota,'quota_counter_conflict':quota_conflict})
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        message=('Instagram Stories incomplete: publishing quota reached; wait for capacity; no automatic retry'
                 if quota_failure else 'Instagram Stories failed at '+stage)
        if quota_conflict:
            message='Instagram Stories incomplete: Meta publishing-limit refusal despite reported spare quota; no automatic retry'
        problem=SafeError(message,stage,reason='instagram_publishing_limit' if quota_failure else None)
        problem.quota_counter_conflict=quota_conflict
        raise problem from None
