"""Straight-line Facebook Page photo publication and actual post verification."""
import os
from urllib.parse import urlparse
from .core import ROOT, require_publishing, write_json
from .http import SafeError
from .meta import Facebook
from .notify import failure


def caption(package):
    return package['caption']+'\n\n'+' '.join(package['hashtags'])


def verify_post(facebook, package, post_id, photo_ids):
    actual=facebook.post(post_id)
    if actual.get('id')!=post_id or actual.get('from',{}).get('id')!=facebook.page_id:
        raise ValueError('Facebook returned a post from another Page')
    if actual.get('message')!=caption(package) or actual.get('is_published') is not True:
        raise ValueError('Facebook post is unpublished or has a different caption')
    photos=[p for attachment in actual.get('attachments',{}).get('data',[]) for p in attachment.get('subattachments',{}).get('data',[])]
    if len(photos)!=3 or [str(p.get('target',{}).get('id','')) for p in photos]!=photo_ids or any(p.get('type')!='photo' for p in photos):
        raise ValueError('Facebook post differs from the three submitted photos in order')
    url=urlparse(actual.get('permalink_url',''))
    if url.scheme!='https' or url.hostname not in ('www.facebook.com','facebook.com','m.facebook.com') or not url.path.strip('/'):
        raise ValueError('Facebook returned no publication permalink')
    return actual['permalink_url']


def publish_facebook(package, assets, record=None):
    date=package['date'];stage='Facebook authorization';result={'batch':date,'published':False}
    publication='nothing published to Facebook'
    try:
        require_publishing()
        if os.getenv('FACEBOOK_POSTING_ENABLED')!='true': raise ValueError('Facebook publisher is disabled')
        facebook=Facebook();facebook.verify_page();photo_ids=[]
        stage='Facebook photo upload'
        for card in package['cards']:
            photo_id=facebook.photo(assets[card['kind']]['url'],card['alt_text']);photo_ids.append(photo_id)
            if record: record('photo',photo_id,facebook.page_id)
        result['photo_ids']=photo_ids;stage='Facebook publishing';require_publishing()
        publication='Facebook publish request outcome uncertain'
        post_id=facebook.publish(photo_ids,caption(package));result['post_id']=post_id
        if record: record('feed',post_id,facebook.page_id)
        stage='Facebook publication verification';publication='published to Facebook; content read-back pending'
        result.update(permalink=verify_post(facebook,package,post_id,photo_ids),published=True,status='confirmed Facebook publication')
        write_json(ROOT/'build'/date/'facebook-result.json',result);return result
    except Exception as error:
        result.update(status=publication,failed_stage=stage);write_json(ROOT/'build'/date/'facebook-result.json',result)
        print(failure(date,stage,error,publication,os.getenv('GITHUB_RUN_URL')))
        raise SafeError('Facebook failed at '+stage,stage) from None
