"""Publish the current run's exact Instagram cards as padded image Stories."""
import os
from urllib.parse import urlparse
from PIL import Image
from .core import ROOT, read_json, require_publishing, write_json
from .http import SafeError, request
from .meta import Instagram
from .notify import failure

HIGHLIGHTS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}


def story_image(source,destination,palette):
    with Image.open(source) as image:
        if image.size!=(1080,1350): raise ValueError('Story source must be the 1080×1350 published card')
        canvas=Image.new('RGB',(1080,1920),palette['panel']);canvas.paste(image.convert('RGB'),(0,285))
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


def publish_stories(store,package,assets):
    date=package['date'];stage='Instagram Stories authorization';stories=[]
    publication='nothing published to Instagram Stories'
    try:
        require_publishing()
        if os.getenv('INSTAGRAM_STORIES_ENABLED')!='true': raise ValueError('Story publisher is disabled')
        ig=Instagram();ig.refresh_if_needed();ig.verify_account()
        palette=read_json(ROOT/'data/design-palettes.json')[package['design_palette']]
        for card in package['cards']:
            kind=card['kind'];stage='Instagram Stories rendering'
            path=ROOT/'build'/date/f'{kind}-story.jpg';story_image(assets[kind]['path'],path,palette)
            store.put_file(date,path.name,path.read_bytes());url=store.expose(date,path.name)
            if request('GET',url,raw=True)!=path.read_bytes(): raise ValueError('Story bytes differ from the padded card')
            stage='Instagram Stories publishing';require_publishing();container=ig.story(url);ig.ready(container)
            publication='partial or uncertain Instagram Story publication'
            media_id=ig.publish(container)
            item={'slide':kind,'media_id':media_id,'highlight':HIGHLIGHTS[kind],'highlight_status':'manual addition required'}
            stories.append(item);stage='Instagram Stories verification';item['permalink']=verify_story(ig,media_id)
        result={'batch':date,'published':True,'status':'three image Stories confirmed published; Highlights need manual addition','stories':stories}
        write_json(ROOT/'build'/date/'instagram-stories-result.json',result);return result
    except Exception as error:
        write_json(ROOT/'build'/date/'instagram-stories-result.json',{'batch':date,'status':publication,'stories':stories,'failed_stage':stage})
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Instagram Stories failed at '+stage,stage) from None
