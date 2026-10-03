"""Publish reviewed Instagram Stories: quiz treatment A, lesson/word treatment B."""
from .batches import output_key
import os
from urllib.parse import urlparse
from PIL import Image, ImageFilter, ImageOps
from .core import ROOT, read_json, require_publishing, write_json
from .http import SafeError, request
from .meta import Instagram
from .notify import failure
from .story_layouts import tall_story_image

HIGHLIGHTS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}


def story_image(source,destination,palette,background=None,card=None):
    if card and (card['kind'] in ('lesson','word') or card.get('quiz_format') == 'visual_identification'):
        return tall_story_image(card,background,destination,palette)
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
    publication='nothing published to Instagram Stories'
    try:
        require_publishing()
        if os.getenv('INSTAGRAM_STORIES_ENABLED')!='true': raise ValueError('Story publisher is disabled')
        ig=Instagram();ig.refresh_if_needed();ig.verify_account()
        palette=read_json(ROOT/'data/design-palettes.json')[package['design_palette']]
        for card in package['cards']:
            kind=card['kind'];stage='Instagram Stories rendering'
            path=ROOT/'build'/output_key(package)/f'{kind}-story.jpg';story_image(assets[kind]['path'],path,palette,assets[kind].get('background_path'),card)
            store.put_file(output_key(package),path.name,path.read_bytes());url=store.expose(output_key(package),path.name)
            if request('GET',url,raw=True)!=path.read_bytes(): raise ValueError('Story bytes differ from the rendered Story')
            stage='Instagram Stories container creation';require_publishing();container=ig.story(url)
            diagnostic={'slide':kind,'container_id':container};containers.append(diagnostic)
            stage='Instagram Stories readiness';diagnostic['ready_status']=ig.ready(container,stable=True)
            stage='Instagram Stories publishing';require_publishing()
            publication='partial or uncertain Instagram Story publication'
            media_id=ig.publish(container)
            if record: record('story',media_id,ig.user_id)
            item={'slide':kind,'media_id':media_id,'highlight':HIGHLIGHTS[kind],'highlight_status':'manual addition required'}
            stories.append(item);stage='Instagram Stories verification';item['permalink']=verify_story(ig,media_id)
        result={'batch':date,'batch_id':package.get('batch_id'),'published':True,'status':'three image Stories confirmed published; Highlights need manual addition','stories':stories}
        write_json(ROOT/'build'/output_key(package)/'instagram-stories-result.json',result);return result
    except Exception as error:
        if containers and stage=='Instagram Stories publishing':
            try:
                containers[-1]['status_after_failure']=ig.call('GET',containers[-1]['container_id'],{'fields':'status_code'}).get('status_code')
            except Exception:
                containers[-1]['status_readback']='unavailable; no retry'
        write_json(ROOT/'build'/output_key(package)/'instagram-stories-result.json',{'batch':date,'batch_id':package.get('batch_id'),'status':publication,'stories':stories,'containers':containers,'failed_stage':stage})
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Instagram Stories failed at '+stage,stage) from None
