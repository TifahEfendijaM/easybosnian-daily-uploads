"""One Instagram publication per invocation, with immediate content read-back."""
import os
from urllib.parse import urlparse
from .core import ROOT, require_publishing, write_json
from .http import SafeError
from .meta import Instagram
from .notify import failure


def verify_media(ig, package, media_id):
    actual=ig.media(media_id)
    expected=package['caption']+'\n\n'+' '.join(package['hashtags'])
    if actual.get('id')!=media_id or actual.get('caption','')!=expected or actual.get('media_type')!='CAROUSEL_ALBUM':
        raise ValueError('Instagram post identity, caption or carousel type differs from reviewed content')
    children=actual.get('children',{}).get('data',[])
    if len(children)!=3 or any(c.get('media_type')!='IMAGE' for c in children):
        raise ValueError('Instagram post must contain three image slides')
    url=urlparse(actual.get('permalink',''))
    if url.scheme!='https' or url.hostname!='www.instagram.com' or not url.path.startswith('/p/'):
        raise ValueError('Instagram returned no actual carousel permalink')
    return actual['permalink']


def publish_instagram(package, assets, record=None):
    date=package['date']; stage='authorization'; result={'batch':date,'published':False}
    publication='nothing published to Instagram'
    try:
        require_publishing()
        ig=Instagram(); ig.refresh_if_needed(); ig.verify_account()
        stage='publishing'; children=[]
        for card in package['cards']:
            child=ig.child(assets[card['kind']]['url'],card['alt_text']);children.append(child);ig.ready(child)
        carousel=ig.carousel(children,package['caption']+'\n\n'+' '.join(package['hashtags']))
        result.update(child_ids=children,container_id=carousel);ig.ready(carousel)
        require_publishing()
        publication='Instagram publish request outcome uncertain'
        media_id=ig.publish(carousel);result['media_id']=media_id
        if record: record('feed',media_id,ig.user_id)
        publication='published to Instagram; content read-back pending';stage='publication verification'
        result.update(permalink=verify_media(ig,package,media_id),published=True,status='confirmed Instagram publication')
        write_json(ROOT/'build'/date/'instagram-result.json',result)
        return result
    except Exception as error:
        result.update(status=publication,failed_stage=stage)
        write_json(ROOT/'build'/date/'instagram-result.json',result)
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Instagram failed at '+stage,stage) from None
